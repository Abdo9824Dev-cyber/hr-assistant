"""Day 13: full evaluation with an AI judge.

For each of the 50 questions in eval/questions.csv (asked as an EMPLOYEE, each one --repeat times):
  - answerable questions: a separate Gemini "judge" compares the answer with the expected answer
      correct   = same key facts (numbers, durations, conditions)
      partial   = right direction but a key fact or condition is missing
      incorrect = wrong fact, contradiction, or "contact HR" when it should have answered
    + framing: does the first word (Yes/No) match the real answer?
    + citation: was the expected document among the cited sources?
  - should-defer questions: must say "contact HR" (a law-only answer is fine for "defer" and "role";
    never for "strict"), and an employee must never see a confidential (CONF-) source.
  - consistency: with --repeat 2+, did every run of a question get the same verdict?

Usage (from the project root, with .venv and .env loaded):
    python eval/run_eval.py                 # 50 questions x 2 runs (~12 minutes, about $0.50)
    python eval/run_eval.py --repeat 1      # faster, no consistency check
    python eval/run_eval.py --only Q37,Q41  # re-run a few questions after a fix
    python eval/run_eval.py --rejudge eval/results/eval_<date>.csv   # grade saved answers again (no questions asked)
Judge model: JUDGE_MODEL (default gemini-2.5-pro); if it isn't available, the answer model is used instead.
Writes eval/results/eval_<date>.csv (every run), eval/results/summary.md and summary_<model>.md.
Compare models: RAG_MODEL=claude-haiku-5-5 python eval/run_eval.py   (prices in eval/prices.json)
"""
import csv
import json
import os
import pathlib
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime

from google.genai import types
from pydantic import BaseModel

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from rag import LAW_ENGINE, MODEL, ask, is_arabic, llm  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "results"
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gemini-2.5-pro")   # a stronger model grades the answers
PAUSE = float(os.environ.get("SMOKE_PAUSE", "1"))


def arg(name: str, default: str = "") -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


REPEAT = int(arg("--repeat", "2"))
REJUDGE = arg("--rejudge")
_judge_model = [JUDGE_MODEL]
ONLY = {q.strip() for q in arg("--only").split(",") if q.strip()}

JUDGE = """You grade answers of an HR assistant for a company in Saudi Arabia. Questions and answers may be
in Arabic or English; grade the meaning, not the wording or language.

Compare ANSWER with EXPECTED. Key facts are only those needed to answer the QUESTION as asked; facts in
EXPECTED that the question did not ask about are optional (e.g. a question about the first year does not
need the rule for year five).
- "correct": the answer states the same key facts as EXPECTED (numbers, durations, amounts, conditions).
  Extra correct detail is fine. A different but equivalent wording is fine.
- "partial": the main fact is right but a key condition or number from EXPECTED is missing.
- "incorrect": a wrong number or fact, a contradiction, or a refusal ("contact HR") when EXPECTED has an answer.

"framing_ok": false only if the answer STARTS with Yes/No (or نعم/لا) and that first word misleads,
i.e. it contradicts or oversimplifies a conditional answer (e.g. starts with "Yes" when it is only allowed
with approval, or "No" when it is allowed in some cases). Otherwise true.

Reply in JSON only."""


class Verdict(BaseModel):
    verdict: str          # correct | partial | incorrect
    framing_ok: bool
    reason: str


def judge(question: str, expected: str, answer: str) -> Verdict:
    for attempt in range(3):
        try:
            r = llm.models.generate_content(
                model=_judge_model[0],
                contents=f"QUESTION: {question}\nEXPECTED: {expected}\nANSWER: {answer}",
                config=types.GenerateContentConfig(
                    system_instruction=JUDGE, temperature=0, response_mime_type="application/json",
                    response_schema=Verdict,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
            v = r.parsed if isinstance(r.parsed, Verdict) else Verdict.model_validate_json(r.text or "")
            v.verdict = v.verdict.lower().strip()
            if v.verdict not in ("correct", "partial", "incorrect"):
                v.verdict = "incorrect"
            return v
        except Exception as e:
            if ("404" in str(e) or "NOT_FOUND" in str(e)) and _judge_model[0] != MODEL:
                print(f"   (judge model {_judge_model[0]} isn't available - using {MODEL} instead)")
                _judge_model[0] = MODEL
                continue
            if attempt == 2:
                return Verdict(verdict="error", framing_ok=True, reason=f"judge failed: {str(e)[:80]}")
            time.sleep(10 * (attempt + 1))


def ask_retry(question: str) -> tuple:
    for attempt in range(3):
        try:
            start = time.perf_counter()
            res = ask(question, role="employee")
            return res, int((time.perf_counter() - start) * 1000)
        except Exception as e:
            if attempt == 2:
                raise
            print(f"   (temporary error, retrying: {str(e)[:60]})")
            time.sleep(10 * (attempt + 1))


def grade(row: dict, res: dict) -> dict:
    cited = [s["title"] for s in res["sources"]]
    law_only = res["grounded"] and all(s.get("kind") == "law" for s in res["sources"])
    leaked = any(t.startswith("CONF-") for t in cited)
    out = {"cited": " | ".join(cited), "basis": res.get("basis", ""), "grounded": res["grounded"],
           "same_language": is_arabic(res["answer"]) == (row["lang"] == "ar"), "leak": leaked,
           "citation_ok": "", "framing_ok": True, "reason": ""}
    kind = row["should_defer"]
    if kind == "strict":
        out["verdict"] = "correct" if not res["grounded"] else "incorrect"
        out["reason"] = "must say contact HR"
    elif kind in ("yes", "role"):
        ok = (not res["grounded"] or law_only) and not leaked
        out["verdict"] = "correct" if ok else "incorrect"
        out["reason"] = "contact HR or Labor Law only" + (" - CONFIDENTIAL LEAK" if leaked else "")
    else:
        v = judge(row["question"], row["expected_answer"], res["answer"])
        out.update(verdict=v.verdict, framing_ok=v.framing_ok, reason=v.reason)
        out["citation_ok"] = row["expected_source"] in cited
    return out


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d:.0%})" if d else "-"


def rejudge(path: str) -> list:
    """Grade the answers saved in an earlier results file again (e.g. after the judge failed)."""
    runs = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    for i, r in enumerate(runs, 1):
        if r["should_defer"] == "no":
            v = judge(r["question"], r["expected_answer"], r["answer"])
            r.update(verdict=v.verdict, framing_ok=v.framing_ok, reason=v.reason)
            print(f"[{i}/{len(runs)}] {v.verdict:<9} {r['id']} {r['question'][:60]}")
        for k in ("framing_ok", "grounded", "same_language", "leak"):
            r[k] = r[k] if isinstance(r[k], bool) else str(r[k]) == "True"
        r["citation_ok"] = "" if r["citation_ok"] == "" else str(r["citation_ok"]) == "True"
        r["latency_ms"] = int(r["latency_ms"])
        r["tokens_in"], r["tokens_out"] = int(r.get("tokens_in") or 0), int(r.get("tokens_out") or 0)
    return runs


def main() -> None:
    rows = [r for r in csv.DictReader((HERE / "questions.csv").open(encoding="utf-8-sig"))
            if not ONLY or r["id"] in ONLY]
    OUT.mkdir(exist_ok=True)
    if not LAW_ENGINE and not REJUDGE:
        sys.exit("LAW_ENGINE_ID is not set - load .env first (set -a && source .env && set +a). "
                 "Without it the Labor Law questions can't be answered.")
    runs = rejudge(REJUDGE) if REJUDGE else []
    if REJUDGE:
        ids = {r["id"] for r in runs}
        rows = [r for r in rows if r["id"] in ids]
    else:
        print(f"Evaluating {len(rows)} questions x {REPEAT} run(s). Model: {MODEL}, judge: {JUDGE_MODEL}\n")
    for i, row in enumerate([] if REJUDGE else rows, 1):
        for k in range(REPEAT):
            res, latency = ask_retry(row["question"])
            g = grade(row, res)
            usage = res.get("usage") or {}
            runs.append({**row, "run": k + 1, "model": res.get("model", MODEL), "answer": res["answer"], "latency_ms": latency,
                         "tokens_in": usage.get("input", 0), "tokens_out": usage.get("output", 0), **g})
            mark = {"correct": "PASS", "partial": "PART", "incorrect": "FAIL"}.get(g["verdict"], "ERR ")
            extra = "" if g["framing_ok"] else "  !! misleading Yes/No"
            extra += "" if g["citation_ok"] in ("", True) else "  !! expected source not cited"
            print(f"[{i}/{len(rows)}] {mark} {row['id']} {row['category']:<11} {row['question'][:60]}{extra}")
            if g["verdict"] != "correct":
                print(f"      answer: {res['answer'][:150]}\n      judge:  {g['reason'][:150]}")
            time.sleep(PAUSE)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    with (OUT / f"eval_{stamp}.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(runs[0].keys()))
        w.writeheader()
        w.writerows(runs)

    # ---- metrics
    answerable = [r for r in runs if r["should_defer"] == "no"]
    deferral = [r for r in runs if r["should_defer"] != "no"]
    correct = sum(r["verdict"] == "correct" for r in answerable)
    partial = sum(r["verdict"] == "partial" for r in answerable)
    by_q = defaultdict(list)
    for r in runs:
        by_q[r["id"]].append((r["verdict"], r["grounded"]))
    consistent = sum(len(set(v)) == 1 for v in by_q.values())
    lat = sorted(r["latency_ms"] for r in runs)
    p90 = lat[min(len(lat) - 1, int(len(lat) * 0.9))]
    cats = Counter(r["category"] for r in runs)
    cat_ok = Counter(r["category"] for r in runs if r["verdict"] == "correct")

    lines = [f"# Evaluation results — {datetime.now():%Y-%m-%d %H:%M}", "",
             f"{len(rows)} questions ({sum(r['lang'] == 'ar' for r in rows)} Arabic, "
             f"{sum(r['lang'] == 'en' for r in rows)} English), {len(runs) // max(1, len(rows))} run(s) each, asked as an employee. "
             f"Answer model `{MODEL}`, judge model `{_judge_model[0]}`.", "",
             "| Metric | Result |", "|---|---|",
             f"| Answer accuracy (judge: correct) | {pct(correct, len(answerable))} |",
             f"| Partially correct | {pct(partial, len(answerable))} |",
             f"| Correct source cited | {pct(sum(r['citation_ok'] is True for r in answerable), len(answerable))} |",
             f"| Correct 'contact HR' behaviour | {pct(sum(r['verdict'] == 'correct' for r in deferral), len(deferral))} |",
             f"| Confidential leaks to employees | {sum(r['leak'] for r in runs)} |",
             f"| Answer in the question's language | {pct(sum(r['same_language'] for r in runs), len(runs))} |",
             f"| No misleading Yes/No | {pct(sum(r['framing_ok'] for r in answerable), len(answerable))} |"]
    if len(runs) > len(rows):
        lines.append(f"| Consistent across runs | {pct(consistent, len(by_q))} |")
    lines.append(f"| Response time (median / 90th percentile) | {statistics.median(lat) / 1000:.1f} s / {p90 / 1000:.1f} s |")
    model = (runs[0].get("model") or MODEL) if runs else MODEL
    try:
        price = json.loads((HERE / "prices.json").read_text())[model]
    except Exception:
        price = None
    t_in = sum(r["tokens_in"] for r in runs) / max(1, len(runs))
    t_out = sum(r["tokens_out"] for r in runs) / max(1, len(runs))
    if t_in:
        lines.append(f"| Answer-model tokens per question (in / out) | {t_in:,.0f} / {t_out:,.0f} |")
    if price and t_in:
        per_1000 = 1000 * (t_in * price["input"] + t_out * price["output"]) / 1_000_000
        lines.append(f"| Answer-model cost per 1,000 questions (estimate) | ${per_1000:.2f} |")
    lines += ["",
              "", "## By category", "", "| Category | Correct |", "|---|---|"]
    lines += [f"| {c} | {pct(cat_ok[c], n)} |" for c, n in sorted(cats.items())]
    fails = [r for r in runs if r["verdict"] != "correct" or not r["framing_ok"]]
    if fails:
        lines += ["", "## To review", "", "| ID | Question | Verdict | Judge's reason |", "|---|---|---|---|"]
        lines += [f"| {r['id']} | {r['question'][:70]} | {r['verdict']} | {r['reason'][:110].replace('|', '/')} |"
                  for r in fails]
    text = "\n".join(lines) + "\n"
    (OUT / "summary.md").write_text(text, encoding="utf-8")
    (OUT / f"summary_{model}.md").write_text(text, encoding="utf-8")   # keep one per model, to compare
    print("\n" + "\n".join(lines[4:lines.index("## By category") - 1]))
    print(f"\nSaved eval/results/eval_{stamp}.csv and eval/results/summary.md")


if __name__ == "__main__":
    main()

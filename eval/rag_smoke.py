"""Day 4 smoke test: run every seed question through the full RAG pipeline.

Checks, per question:
  - answerable questions: did it answer (not defer) and cite the expected policy?
  - should-defer / HR-only questions: did it correctly say "contact HR"?
Answer correctness is judged by you (expected vs actual are printed side by side);
an automatic judge comes on Day 13.

Usage (from the project root): python eval/rag_smoke.py
"""
import csv
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from rag import ask  # noqa: E402

QUESTIONS = pathlib.Path("eval/questions_seed.csv")
RESULTS = pathlib.Path("eval/rag_results.csv")
PAUSE = float(os.environ.get("SMOKE_PAUSE", "2"))  # seconds between questions, avoids rate limits


def ask_with_retry(question: str, tries: int = 4) -> dict:
    for attempt in range(tries):
        try:
            return ask(question)
        except Exception as e:  # rate limits or a temporary error: wait and retry
            if attempt == tries - 1:
                raise
            wait = 10 * (attempt + 1)
            print(f"   (retrying in {wait}s: {str(e)[:80]})")
            time.sleep(wait)


def main() -> None:
    rows = list(csv.DictReader(QUESTIONS.open(encoding="utf-8-sig")))
    out = []
    for i, r in enumerate(rows, 1):
        if i > 1:
            time.sleep(PAUSE)
        res = ask_with_retry(r["question"])
        cited = [s["title"] for s in res["sources"]]
        if r["should_defer"] == "no":
            ok = res["grounded"] and r["expected_source"] in cited
            kind = "answer"
        else:  # "yes" (not in documents) and "role" (HR-only docs are not in this index yet)
            ok = not res["grounded"]
            kind = "defer"
        print(f"\n[{i}/{len(rows)}] {'PASS' if ok else 'FAIL'} ({kind}) [{r['lang']}] {r['question']}")
        print(f"   expected: {r['expected_answer']}")
        print(f"   answer:   {res['answer']}")
        print(f"   sources:  {', '.join(cited) or '-'}")
        if not ok:
            print(f"   search found: {', '.join(res.get('retrieved', [])) or '(nothing)'}")
        out.append({"lang": r["lang"], "question": r["question"], "kind": kind,
                    "expected_answer": r["expected_answer"], "answer": res["answer"],
                    "expected_source": r["expected_source"], "sources": " | ".join(cited),
                    "search_found": " | ".join(res.get("retrieved", [])),
                    "pass": ok})

    answer_rows = [o for o in out if o["kind"] == "answer"]
    defer_rows = [o for o in out if o["kind"] == "defer"]
    a = sum(o["pass"] for o in answer_rows)
    d = sum(o["pass"] for o in defer_rows)
    print("\n| Check | Result |")
    print("|---|---|")
    print(f"| Answered with the correct source cited | {a}/{len(answer_rows)} ({a/len(answer_rows):.0%}) |")
    print(f"| Correctly said 'contact HR' | {d}/{len(defer_rows)} ({d/len(defer_rows):.0%}) |")
    with RESULTS.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    print(f"\nDetails saved to {RESULTS}. Now read the answers: are the numbers right?")


if __name__ == "__main__":
    main()

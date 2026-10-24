"""Day 7: bilingual consistency test.

The same 12 questions are asked in English and in Arabic. A pair passes when BOTH versions:
  - are answered (not "contact HR"),
  - cite the expected policy,
  - come back in the question's language.
Both answers are printed side by side so you can check they say the same thing (same numbers).

Usage (from the project root): python eval/bilingual_test.py
"""
import csv
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from rag import ask, is_arabic  # noqa: E402

PAIRS = pathlib.Path("eval/bilingual_pairs.csv")
RESULTS = pathlib.Path("eval/bilingual_results.csv")
PAUSE = float(os.environ.get("SMOKE_PAUSE", "2"))


def check(question: str, expected: str, want_arabic: bool) -> tuple:
    res = ask(question)
    cited = [s["title"] for s in res["sources"]]
    ok = res["grounded"] and expected in cited and is_arabic(res["answer"]) == want_arabic
    return ok, res


def main() -> None:
    rows = list(csv.DictReader(PAIRS.open(encoding="utf-8")))
    out, passed = [], 0
    for i, r in enumerate(rows, 1):
        ok_en, en = check(r["question_en"], r["expected_source"], want_arabic=False)
        time.sleep(PAUSE)
        ok_ar, ar = check(r["question_ar"], r["expected_source"], want_arabic=True)
        time.sleep(PAUSE)
        pair_ok = ok_en and ok_ar
        passed += pair_ok
        print(f"\n[{i}/{len(rows)}] {'PASS' if pair_ok else 'FAIL'}  expected: {r['expected_source']}")
        print(f"   EN {'ok ' if ok_en else 'BAD'} {r['question_en']}\n      -> {en['answer']}")
        print(f"   AR {'ok ' if ok_ar else 'BAD'} {r['question_ar']}\n      -> {ar['answer']}")
        out.append({"expected_source": r["expected_source"],
                    "question_en": r["question_en"], "answer_en": en["answer"], "ok_en": ok_en,
                    "question_ar": r["question_ar"], "answer_ar": ar["answer"], "ok_ar": ok_ar,
                    "pair_ok": pair_ok})
    print(f"\n| Bilingual pairs consistent | {passed}/{len(rows)} ({passed/len(rows):.0%}) |")
    with RESULTS.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    print(f"Details saved to {RESULTS}. Check that each EN/AR pair gives the same facts.")


if __name__ == "__main__":
    main()

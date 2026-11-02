"""Day 11: Saudi Labor Law layer test.

Checks, per question:
  - it answered (or deferred) as expected,
  - the answer came from the expected place: company policy, the law, or both,
  - the key fact is in the answer (a loose keyword check - read the answers yourself too),
  - no false "conflict with the law" flags.

Usage (from the project root, with LAW_ENGINE_ID in .env):
    python eval/law_test.py              # the main checks
    python eval/law_test.py --conflict   # after uploading EN-07_Maternity_Leave_Policy.pdf (10 weeks, outdated):
                                         # the assistant must flag that the law requires more
"""
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from rag import LAW_ENGINE, _norm  # noqa: E402
from rag import ask as _ask  # noqa: E402

if not LAW_ENGINE:
    sys.exit("LAW_ENGINE_ID is not set in .env - run infra/setup_law.py first.")
PAUSE = float(os.environ.get("SMOKE_PAUSE", "2"))

# (question, accepted bases, keywords - at least one must appear, expect law_conflict)
CASES = [
    # The company policy only says "according to the Saudi Labor Law" -> the law must fill in the numbers
    ("How is the end-of-service award calculated?", {"law", "both"}, ["half", "نصف"], False),
    ("If I resign after 3 years, how much of the end-of-service award do I get?", {"law", "both"},
     ["third", "1/3", "ثلث"], False),
    ("كيف يتم احتساب أجر الإجازة المرضية؟", {"law", "both"}, ["ثلاثة أرباع", "75", "3/4"], False),
    # Not in the company policies at all -> answered from the law
    # (maternity moved to --conflict: once EN-07 is uploaded the policy covers it, and conflicts with the law)
    ("ما مدة الإشعار إذا أنهى صاحب العمل عقداً غير محدد المدة؟", {"law", "both"}, ["60", "٦٠", "ستين", "ستون"], False),
    ("Can my employer deduct money from my salary?", {"law", "both"}, [], False),
    ("متى يجوز لصاحب العمل فصل العامل دون مكافأة؟", {"law"}, [], False),
    # Covered by company policy (which meets the law) -> policy answer, no conflict
    ("How many days of annual leave do I get?", {"policy", "both"}, [], False),
    ("كم يوم إجازة الأب عند ولادة مولود؟", {"policy", "both"}, ["3", "٣", "ثلاثة"], False),
    # Must never invent
    ("What does Article 999 of the Labor Law say?", {"none"}, [], False),
]
CONFLICT_CASES = [
    ("How many weeks of maternity leave do I get?", {"both"}, ["12", "twelve"], True),
    ("كم أسبوعاً مدة إجازة الأمومة؟", {"both"}, ["12", "١٢", "اثني عشر", "اثنا عشر"], True),
]


def ask(question: str, tries: int = 3) -> dict:
    for attempt in range(tries):
        try:
            return _ask(question, role="employee")
        except Exception as e:
            if attempt == tries - 1:
                raise
            print(f"    (temporary error, retrying in {10 * (attempt + 1)}s: {str(e)[:70]})")
            time.sleep(10 * (attempt + 1))


cases = CONFLICT_CASES if "--conflict" in sys.argv else CASES
passed = articles = law_answers = 0
for i, (q, bases, keywords, conflict) in enumerate(cases, 1):
    if i > 1:
        time.sleep(PAUSE)
    res = ask(q)
    basis = res.get("basis", "none")
    answer = _norm(res["answer"])
    basis_ok = basis in bases
    fact_ok = not keywords or any(_norm(k) in answer for k in keywords)
    conflict_ok = bool(res.get("law_conflict")) == conflict
    ok = basis_ok and fact_ok and conflict_ok
    passed += ok
    if basis in ("law", "both"):
        law_answers += 1
        articles += ("article" in answer or "المادة" in answer or "ماده" in answer)
    print(f"\n[{i}/{len(cases)}] {'PASS' if ok else 'FAIL'}  {q}")
    print(f"   basis: {basis} (expected {' or '.join(sorted(bases))})"
          f"{'' if fact_ok else '   !! key fact missing'}"
          f"{'' if conflict_ok else '   !! wrong conflict flag'}")
    print(f"   answer: {res['answer']}")
    print(f"   sources: {', '.join(s['title'] + (' [law]' if s.get('kind') == 'law' else '') for s in res['sources']) or '-'}")

print("\n| Check | Result |")
print("|---|---|")
print(f"| Labor Law checks passed | {passed}/{len(cases)} |")
if law_answers:
    print(f"| Law answers that name the article | {articles}/{law_answers} |")

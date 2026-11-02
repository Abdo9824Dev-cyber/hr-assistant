"""Day 8: access-control test. The same questions are asked as an employee and as an HR admin.

  - Confidential questions: the employee must get "contact HR" (or, since Day 11, an answer from the public
    Saudi Labor Law only); the HR admin must get an answer citing a confidential document (CONF-...).
    The security rule: an employee must NEVER see a CONF-... document.
  - Normal questions: both roles get the same kind of answer from company policies.

Usage (from the project root, with CONFIDENTIAL_ENGINE_ID in .env): python eval/roles_test.py
"""
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from rag import CONFIDENTIAL_ENGINE  # noqa: E402
from rag import ask as _ask  # noqa: E402

if not CONFIDENTIAL_ENGINE:
    sys.exit("CONFIDENTIAL_ENGINE_ID is not set in .env - create the confidential search app first.")

PAUSE = float(os.environ.get("SMOKE_PAUSE", "2"))


def ask(question: str, role: str, tries: int = 3) -> dict:
    """Ask with retries, so a temporary Google error doesn't stop the whole test."""
    for attempt in range(tries):
        try:
            return _ask(question, role=role)
        except Exception as e:
            if attempt == tries - 1:
                raise
            print(f"    (temporary error, retrying in {10 * (attempt + 1)}s: {str(e)[:70]})")
            time.sleep(10 * (attempt + 1))
CONFIDENTIAL = [
    "What is the salary range for grade 5?",
    "كم نسبة بدل السكن؟",
    "What bonus can a grade 8 employee get?",
    "كم يوم لدى الموظف للتظلم من الجزاء؟",
]
NORMAL = [
    "How many days of annual leave do I get?",
    "كم مدة فترة التجربة؟",
]


def cites_confidential(res: dict) -> bool:
    return any(s["title"].startswith("CONF-") for s in res["sources"])


passed = total = 0
print("Confidential questions (employee: refused or law-only answer; HR admin: confidential answer):")
for q in CONFIDENTIAL:
    emp = ask(q, role="employee"); time.sleep(PAUSE)
    adm = ask(q, role="hr_admin"); time.sleep(PAUSE)
    law_only = emp["grounded"] and all(s.get("kind") == "law" for s in emp["sources"])
    emp_ok = (not emp["grounded"] or law_only) and not cites_confidential(emp)
    adm_ok = adm["grounded"] and cites_confidential(adm)
    total += 2; passed += emp_ok + adm_ok
    print(f"\n  {q}")
    print(f"    employee {'ok ' if emp_ok else 'BAD'} -> {emp['answer']}")
    print(f"    hr_admin {'ok ' if adm_ok else 'BAD'} -> {adm['answer']}  [{', '.join(s['title'] for s in adm['sources'])}]")

print("\nNormal questions (both roles answered from company policies):")
for q in NORMAL:
    for role in ("employee", "hr_admin"):
        res = ask(q, role=role); time.sleep(PAUSE)
        ok = res["grounded"] and not cites_confidential(res)
        total += 1; passed += ok
        print(f"  {role:<8} {'ok ' if ok else 'BAD'} {q} -> {res['answer'][:90]}")

print(f"\n| Access-control checks passed | {passed}/{total} |")
if passed < total:
    print("Any BAD line in the employee rows is a SECURITY problem - fix before deploying.")

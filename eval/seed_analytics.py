"""Fill the analytics dashboard with realistic demo data (for screenshots and client demos).

Asks real questions through the assistant (so answers and sources are genuine), as employees from
different departments, with dates spread over the last 14 days. Every record is flagged demo=True.

Usage (from the project root, with .venv and .env loaded):
    python eval/seed_analytics.py            # about 70 questions, ~4 minutes, a few cents of usage
    python eval/seed_analytics.py --delete   # remove all demo records again
"""
import csv
import os
import pathlib
import random
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
import analytics  # noqa: E402
from rag import ask  # noqa: E402

random.seed(7)
HERE = pathlib.Path(__file__).resolve().parent
DEPARTMENTS = ["Finance", "Sales", "Warehouse", "IT", "HR"]
PAUSE = float(os.environ.get("SMOKE_PAUSE", "1"))

# Questions the policies don't cover - they show up as "policy gaps" on the dashboard.
GAPS = [
    "Does the company provide medical insurance for my family?",
    "هل يوجد تأمين طبي لعائلتي؟",
    "Can I bring my child to the office?",
    "هل توفر الشركة سيارة للموظفين؟",
    "What is the policy on company cars?",
    "Is there a gym allowance?",
    "هل يوجد بدل نادي رياضي؟",
]


def questions() -> list:
    qs = [r["question"] for r in csv.DictReader((HERE / "questions_seed.csv").open(encoding="utf-8-sig"))
          if r["should_defer"] == "no"]
    pairs = list(csv.DictReader((HERE / "bilingual_pairs.csv").open(encoding="utf-8")))
    qs += [p["question_en"] for p in pairs] + [p["question_ar"] for p in pairs]
    # Popular topics get asked more than once (that's what "top questions" shows)
    popular = ["How many days of annual leave do I get?", "كم مدة فترة التجربة؟",
               "What is the hotel limit in Jeddah?", "ما هي ساعات العمل في رمضان؟"]
    # Day 11: questions the Saudi Labor Law answers (and a maternity question that shows a conflict
    # once EN-07_Maternity_Leave_Policy is uploaded)
    law = ["How is the end-of-service award calculated?", "كم مدة إجازة الوضع للموظفة؟",
           "If I resign after 3 years, how much of the end-of-service award do I get?",
           "How many weeks of maternity leave do I get?"]
    return qs + popular * 2 + GAPS + GAPS[:3] + law * 2


def seed() -> None:
    qs = questions()
    random.shuffle(qs)
    now = datetime.now(timezone.utc)
    print(f"Asking {len(qs)} questions (demo data)...")
    for i, q in enumerate(qs, 1):
        user = {"role": "employee", "department": random.choice(DEPARTMENTS)}
        start = time.perf_counter()
        for attempt in range(3):
            try:
                result = ask(q, role="employee")
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  skipped (error): {q[:50]} - {str(e)[:60]}")
                    result = None
                else:
                    time.sleep(10)
        if result is None:
            continue
        latency = int((time.perf_counter() - start) * 1000)
        # spread over the last 14 days, more on weekdays, during working hours
        day = random.choices(range(14), weights=[3, 3, 3, 3, 3, 1, 1] * 2)[0]
        when = (now - timedelta(days=day)).replace(hour=random.randint(5, 14), minute=random.randint(0, 59))
        analytics.record(q, result, user, latency, when=min(when, now), demo=True)
        print(f"  [{i}/{len(qs)}] {'answered' if result['grounded'] else 'to HR   '}  {q[:60]}")
        time.sleep(PAUSE)
    print("Done. Open the dashboard to see the results.")


def delete() -> None:
    from google.cloud.firestore_v1.base_query import FieldFilter
    col = analytics.db().collection(analytics.COLLECTION)
    n = 0
    for snap in col.where(filter=FieldFilter("demo", "==", True)).stream():
        snap.reference.delete()
        n += 1
    print(f"Deleted {n} demo records.")


if __name__ == "__main__":
    delete() if "--delete" in sys.argv else seed()

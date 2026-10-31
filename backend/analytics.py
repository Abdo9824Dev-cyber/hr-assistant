"""Day 10: anonymous question analytics for HR.

Every answered question is recorded in Firestore, collection "chats", WITHOUT the user's identity:
    question, q_norm (for grouping), lang, grounded (answered vs sent to HR), sources (policy names),
    role, department, latency_ms, created_at, expire_at (auto-delete date), demo (seed data flag)

    GET /admin/analytics?days=30   -> figures for the dashboard (HR admins only)
"""
import logging
import os
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from auth import require_hr_admin
from rag import titles_for

log = logging.getLogger("hr-api")
router = APIRouter(prefix="/admin", tags=["analytics"])
PROJECT = os.environ["PROJECT_ID"]
COLLECTION = os.environ.get("CHATS_COLLECTION", "chats")
RETENTION_DAYS = int(os.environ.get("CHAT_RETENTION_DAYS", "180"))
MAX_ROWS = 20000
_db = None


def db():
    global _db
    if _db is None:
        _db = firestore.Client(project=PROJECT)
    return _db


def normalize(question: str) -> str:
    """Group the same question asked slightly differently: case, punctuation, Arabic letter forms and marks."""
    q = unicodedata.normalize("NFKC", question).lower().replace("ـ", "")
    q = re.sub(r"[ً-ْٰ]", "", q)                    # Arabic diacritics
    q = q.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"}))
    q = re.sub(r"[^\w\s]", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def record(question: str, result: dict, user: dict, latency_ms: int,
           when: datetime | None = None, demo: bool = False) -> None:
    """Save one anonymous question record. Never raises: analytics must not break answering."""
    try:
        now = when or datetime.now(timezone.utc)
        db().collection(COLLECTION).add({
            "question": question[:500],
            "q_norm": normalize(question)[:500],
            "lang": result.get("lang", "en"),
            "grounded": bool(result.get("grounded")),
            "sources": [s.get("title", "") for s in result.get("sources", [])],
            "role": user.get("role", "employee"),
            "department": user.get("department") or "",
            "latency_ms": int(latency_ms),
            "created_at": now,
            "expire_at": now + timedelta(days=RETENTION_DAYS),
            "demo": demo,
        })
    except Exception:
        log.exception("analytics record failed")


def _top(groups: dict, limit: int) -> list:
    """groups: q_norm -> list of original questions. Most frequent first; show the most common wording."""
    rows = [{"question": Counter(qs).most_common(1)[0][0], "count": len(qs)} for qs in groups.values()]
    rows.sort(key=lambda r: (-r["count"], r["question"]))
    return rows[:limit]


def summarize(rows: list, days: int, today: datetime) -> dict:
    total = len(rows)
    answered = sum(r.get("grounded", False) for r in rows)
    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms")]
    by_day = {(today - timedelta(days=i)).date().isoformat(): {"answered": 0, "to_hr": 0} for i in range(days - 1, -1, -1)}
    top, gaps = defaultdict(list), defaultdict(list)
    sources, departments, langs, roles = Counter(), Counter(), Counter(), Counter()
    for r in rows:
        created = r.get("created_at")
        day = created.date().isoformat() if hasattr(created, "date") else None
        if day in by_day:
            by_day[day]["answered" if r.get("grounded") else "to_hr"] += 1
        key = r.get("q_norm") or normalize(r.get("question", ""))
        top[key].append(r.get("question", ""))
        if not r.get("grounded"):
            gaps[key].append(r.get("question", ""))
        for s in r.get("sources", []):
            sources[s] += 1
        departments[r.get("department") or "unassigned"] += 1
        langs[r.get("lang", "en")] += 1
        roles[r.get("role", "employee")] += 1
    return {
        "days": days,
        "demo_records": sum(1 for r in rows if r.get("demo")),
        "total": total,
        "answered": answered,
        "to_hr": total - answered,
        "answer_rate": round(answered / total, 3) if total else None,
        "median_latency_ms": int(statistics.median(latencies)) if latencies else None,
        "languages": dict(langs),
        "roles": dict(roles),
        "by_day": [{"date": d, **v} for d, v in by_day.items()],
        "top_questions": _top(top, 10),
        "unanswered": _top(gaps, 10),
        "top_sources": [{"name": n, "count": c, "title_en": titles_for(n)["en"], "title_ar": titles_for(n)["ar"]}
                        for n, c in sources.most_common(8)],
        "departments": [{"name": n, "count": c} for n, c in departments.most_common(8)],
    }


@router.get("/analytics")
def analytics(days: int = Query(30, ge=1, le=365), user: dict = Depends(require_hr_admin)):
    today = datetime.now(timezone.utc)
    since = (today - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    query = db().collection(COLLECTION).where(filter=FieldFilter("created_at", ">=", since)).limit(MAX_ROWS)
    rows = [snap.to_dict() or {} for snap in query.stream()]
    return summarize(rows, days, today)

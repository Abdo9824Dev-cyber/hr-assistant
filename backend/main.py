"""HR Assistant web service: API + chat page in one Cloud Run service.

Endpoints:
    GET  /         -> the chat page (static/index.html)
    GET  /health   -> status, and whether an access code is required / accepted
    POST /ask      -> {"question": "..."} returns answer, sources, grounded, lang

Run locally (from backend/, with .venv and .env loaded):
    uvicorn main:app --reload --port 8080   then open http://localhost:8080
"""
import hmac
import logging
import os
import pathlib
import time

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from messages import DISCLAIMER
from rag import MODEL, ask

log = logging.getLogger("hr-api")
logging.basicConfig(level=logging.INFO)

RATE_LIMIT = os.environ.get("RATE_LIMIT", "20/minute")
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")   # empty = no code required (local development)
STATIC_DIR = pathlib.Path(__file__).parent / "static"


def client_ip(request: Request) -> str:
    """Real visitor IP. Cloud Run puts it first in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")


limiter = Limiter(key_func=client_ip)
app = FastAPI(title="HR Assistant API", version="0.6.0",
              description="Answers employee questions from company HR policies, in Arabic or English.")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def code_ok(code: str | None) -> bool:
    return not ACCESS_CODE or hmac.compare_digest((code or "").encode(), ACCESS_CODE.encode())


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000,
                          examples=["How many days of annual leave do I get?"])


class Source(BaseModel):
    title: str
    snippet: str


class AnswerOut(BaseModel):
    answer: str
    sources: list[Source]
    grounded: bool
    lang: str
    disclaimer: str
    latency_ms: int


@app.get("/health")
def health(x_access_code: str | None = Header(default=None)):
    return {"ok": True, "model": MODEL,
            "access_code_required": bool(ACCESS_CODE), "access_ok": code_ok(x_access_code)}


@app.post("/ask", response_model=AnswerOut)
@limiter.limit(RATE_LIMIT)
def ask_route(request: Request, q: Question, x_access_code: str | None = Header(default=None)):
    if not code_ok(x_access_code):
        raise HTTPException(status_code=401, detail="Access code required.")
    start = time.perf_counter()
    try:
        result = ask(q.question.strip())
    except Exception:
        log.exception("ask failed")  # details stay in our logs, never sent to the user
        raise HTTPException(status_code=503, detail="The assistant is temporarily unavailable. Please try again.")
    latency = int((time.perf_counter() - start) * 1000)
    log.info("ask lang=%s grounded=%s sources=%d latency_ms=%d",  # metadata only, never the question
             result["lang"], result["grounded"], len(result["sources"]), latency)
    return AnswerOut(
        answer=result["answer"],
        sources=[Source(title=s["title"], snippet=s["snippet"]) for s in result["sources"]],
        grounded=result["grounded"],
        lang=result["lang"],
        disclaimer=DISCLAIMER[result["lang"]],
        latency_ms=latency,
    )


# The chat page. Mounted last so /health, /ask and /docs keep working.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

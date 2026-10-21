"""Day 5: the web API around the RAG core.

Endpoints:
    GET  /health  -> {"ok": true}            (used by Cloud Run and monitoring)
    POST /ask     -> {"question": "..."}      returns answer, sources, grounded, lang

Run locally (from backend/, with .venv and .env loaded):
    uvicorn main:app --reload --port 8080
    then open http://localhost:8080/docs
"""
import logging
import os
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from messages import DISCLAIMER
from rag import MODEL, ask

log = logging.getLogger("hr-api")
logging.basicConfig(level=logging.INFO)

RATE_LIMIT = os.environ.get("RATE_LIMIT", "20/minute")
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("FRONTEND_URL", "*").split(",") if o.strip()]

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="HR Assistant API", version="0.5.0",
              description="Answers employee questions from company HR policies, in Arabic or English.")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["GET", "POST"], allow_headers=["*"])


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
def health():
    return {"ok": True, "model": MODEL}


@app.post("/ask", response_model=AnswerOut)
@limiter.limit(RATE_LIMIT)
def ask_route(request: Request, q: Question):
    start = time.perf_counter()
    try:
        result = ask(q.question.strip())
    except Exception:
        # Log the error type for us, but never return internal details to the user.
        log.exception("ask failed")
        raise HTTPException(status_code=503, detail="The assistant is temporarily unavailable. Please try again.")
    latency = int((time.perf_counter() - start) * 1000)
    # Privacy: log metadata only, never the question or answer text.
    log.info("ask lang=%s grounded=%s sources=%d latency_ms=%d",
             result["lang"], result["grounded"], len(result["sources"]), latency)
    return AnswerOut(
        answer=result["answer"],
        sources=[Source(title=s["title"], snippet=s["snippet"]) for s in result["sources"]],
        grounded=result["grounded"],
        lang=result["lang"],
        disclaimer=DISCLAIMER[result["lang"]],
        latency_ms=latency,
    )
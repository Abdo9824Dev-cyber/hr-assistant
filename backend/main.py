"""HR Assistant web service: API + chat page in one Cloud Run service, with sign-in and roles (Day 8).

Endpoints:
    GET  /         -> the chat page (static/index.html)
    GET  /config   -> public sign-in settings for the page (Identity Platform API key, auth domain)
    GET  /health   -> status
    GET  /me       -> who is signed in and their role               (needs a valid sign-in token)
    POST /ask      -> {"question": "..."} answer for the user's role (needs a valid sign-in token)
    /admin/...     -> document management for HR admins (see admin.py)

Sign-in: the page signs users in with Google Identity Platform and sends "Authorization: Bearer <ID token>".
This server verifies the token's signature and reads the role from it. Roles are set by an admin
(infra/users.py); users cannot choose or edit their own role.

Local development without sign-in: set AUTH_DISABLED=1 (and optionally DEV_ROLE=hr_admin).
Never set AUTH_DISABLED on Cloud Run.

Run locally (from backend/, with .venv and .env loaded):
    uvicorn main:app --reload --port 8080   then open http://localhost:8080
"""
import logging
import os
import pathlib
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from admin import router as admin_router
from auth import AUTH_DISABLED, current_user
from messages import DISCLAIMER
from rag import MODEL, PROJECT, ask

log = logging.getLogger("hr-api")
logging.basicConfig(level=logging.INFO)

RATE_LIMIT = os.environ.get("RATE_LIMIT", "20/minute")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")
FIREBASE_AUTH_DOMAIN = os.environ.get("FIREBASE_AUTH_DOMAIN", f"{PROJECT}.firebaseapp.com")
STATIC_DIR = pathlib.Path(__file__).parent / "static"


def client_key(request: Request) -> str:
    """Rate-limit per signed-in user; fall back to the visitor's IP (first X-Forwarded-For entry on Cloud Run)."""
    uid = getattr(request.state, "uid", None)
    if uid:
        return f"user:{uid}"
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")


limiter = Limiter(key_func=client_key)
app = FastAPI(title="HR Assistant API", version="0.9.0",
              description="Answers employee questions from company HR policies, in Arabic or English.")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(admin_router)   # /admin/... (HR admins only)


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000,
                          examples=["How many days of annual leave do I get?"])


class Source(BaseModel):
    title: str
    title_en: str
    title_ar: str
    snippet: str
    verified: bool


class AnswerOut(BaseModel):
    answer: str
    sources: list[Source]
    grounded: bool
    lang: str
    disclaimer: str
    latency_ms: int


@app.get("/config")
def config():
    """Public settings the page needs to show the sign-in form (these values are not secrets)."""
    return {"auth_disabled": AUTH_DISABLED, "api_key": FIREBASE_API_KEY, "auth_domain": FIREBASE_AUTH_DOMAIN}


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL, "auth": "disabled" if AUTH_DISABLED else "required"}


@app.get("/me")
def me(user: dict = Depends(current_user)):
    return {"email": user["email"], "role": user["role"]}


@app.post("/ask", response_model=AnswerOut)
@limiter.limit(RATE_LIMIT)
def ask_route(request: Request, q: Question, user: dict = Depends(current_user)):
    start = time.perf_counter()
    try:
        result = ask(q.question.strip(), role=user["role"])
    except Exception:
        log.exception("ask failed")  # details stay in our logs, never sent to the user
        raise HTTPException(status_code=503, detail="The assistant is temporarily unavailable. Please try again.")
    latency = int((time.perf_counter() - start) * 1000)
    # Privacy: metadata only - never the question, the answer or the email address.
    log.info("ask role=%s lang=%s grounded=%s sources=%d latency_ms=%d",
             user["role"], result["lang"], result["grounded"], len(result["sources"]), latency)
    return AnswerOut(
        answer=result["answer"],
        sources=[Source(title=s["title"], title_en=s["title_en"], title_ar=s["title_ar"],
                        snippet=s["snippet"], verified=s["verified"]) for s in result["sources"]],
        grounded=result["grounded"],
        lang=result["lang"],
        disclaimer=DISCLAIMER[result["lang"]],
        latency_ms=latency,
    )


# The chat page. Mounted last so the API routes above keep working.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

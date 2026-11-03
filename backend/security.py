"""Day 12: browser security headers for every response.

- Content-Security-Policy: the page may only run our own scripts, the Firebase sign-in library and the small
  inline theme script (allowed by its exact hash, computed from the HTML files at start-up). Injected
  scripts, other sites framing the page, and forms posting elsewhere are all blocked by the browser.
- Plus: no MIME sniffing, no framing, strict referrer, HTTPS only (HSTS), no caching of API answers.
"""
import base64
import hashlib
import pathlib
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

STATIC_DIR = pathlib.Path(__file__).parent / "static"


def _inline_script_hashes() -> list:
    """sha256 of every inline <script> (without src) in our HTML pages, in CSP format."""
    hashes = set()
    for page in STATIC_DIR.glob("*.html"):
        for body in re.findall(r"<script>(.*?)</script>", page.read_text(encoding="utf-8"), flags=re.S):
            digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
            hashes.add(f"'sha256-{digest}'")
    return sorted(hashes)


CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://www.gstatic.com " + " ".join(_inline_script_hashes()),
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",   # inline style="" attributes on icons
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com",
    "frame-src https://*.firebaseapp.com",                               # Firebase sign-in helper frame
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
])

HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}
API_PREFIXES = ("/ask", "/me", "/admin", "/config", "/health")


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for name, value in HEADERS.items():
            response.headers.setdefault(name, value)
        path = request.url.path
        if not path.startswith(("/docs", "/redoc", "/openapi.json")):  # Swagger needs its own scripts (local only)
            response.headers.setdefault("Content-Security-Policy", CSP)
        if path.startswith(API_PREFIXES):
            response.headers["Cache-Control"] = "no-store"   # answers and admin data never stay in caches
        return response

"""Sign-in check shared by the chat API and the admin API.

Every request must carry "Authorization: Bearer <Identity Platform ID token>". We verify the token's
signature with Google and read the role from it. Users cannot choose or edit their own role.
Local development without sign-in: AUTH_DISABLED=1 (optionally DEV_ROLE=hr_admin). Never on Cloud Run.
"""
import logging
import os

import firebase_admin
from fastapi import Depends, HTTPException, Request
from firebase_admin import auth as fb_auth

log = logging.getLogger("hr-api")

PROJECT = os.environ["PROJECT_ID"]
AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
DEV_ROLE = os.environ.get("DEV_ROLE", "employee")
ROLES = {"employee", "hr_admin"}
CHECK_REVOKED = os.environ.get("CHECK_REVOKED", "on").lower() in ("on", "1", "true", "yes")

if not AUTH_DISABLED:
    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": PROJECT})
elif os.environ.get("K_SERVICE"):  # K_SERVICE is set by Cloud Run
    log.warning("AUTH_DISABLED is set on Cloud Run - every visitor is treated as %s!", DEV_ROLE)


def current_user(request: Request) -> dict:
    """Verify the sign-in token and return {uid, email, role}."""
    if AUTH_DISABLED:
        user = {"uid": "dev", "email": "developer@localhost", "role": DEV_ROLE,
                "department": os.environ.get("DEV_DEPARTMENT", "")}
    else:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Sign-in required.")
        try:
            # check_revoked (Day 12): a disabled account or a changed role stops working immediately,
            # not up to an hour later when the old token would expire on its own.
            claims = fb_auth.verify_id_token(header.split(" ", 1)[1].strip(), check_revoked=CHECK_REVOKED)
        except fb_auth.UserDisabledError:
            raise HTTPException(status_code=401, detail="This account is turned off. Contact HR.")
        except Exception:
            raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
        role = claims.get("role", "employee")
        user = {"uid": claims["uid"], "email": claims.get("email", ""),
                "role": role if role in ROLES else "employee",
                "department": str(claims.get("department", ""))[:40]}
    request.state.uid = user["uid"]
    return user


def require_hr_admin(user: dict = Depends(current_user)) -> dict:
    """Only HR admins may continue."""
    if user["role"] != "hr_admin":
        raise HTTPException(status_code=403, detail="Only HR admins can do this.")
    return user

"""Manage HR Assistant accounts and roles (run by an administrator from the project root).

Usage (with .venv and .env loaded):
    python infra/users.py create  someone@company.com employee     # prints a temporary password
    python infra/users.py create  hr.lead@company.com hr_admin
    python infra/users.py role    someone@company.com hr_admin     # change a role
    python infra/users.py list
    python infra/users.py disable someone@company.com              # block sign-in (keeps the account)
    python infra/users.py enable  someone@company.com
    python infra/users.py delete  someone@company.com

Roles: employee (company policies) | hr_admin (company policies + confidential HR files).
A role change applies at the user's next sign-in (or within one hour, when their token refreshes).
"""
import os
import secrets
import string
import sys

import firebase_admin
from firebase_admin import auth

ROLES = ("employee", "hr_admin")
firebase_admin.initialize_app(options={"projectId": os.environ["PROJECT_ID"]})


def temp_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length - 2)) + "!7"


def need_role(role: str) -> str:
    if role not in ROLES:
        sys.exit(f"Role must be one of: {', '.join(ROLES)}")
    return role


def main(args: list) -> None:
    if not args:
        sys.exit(__doc__)
    cmd = args[0]
    if cmd == "create" and len(args) == 3:
        email, role = args[1], need_role(args[2])
        password = temp_password()
        user = auth.create_user(email=email, password=password, email_verified=False)
        auth.set_custom_user_claims(user.uid, {"role": role})
        print(f"Created {email} as {role}")
        print(f"Temporary password: {password}")
        print("Share it privately; the user can change it with 'Forgot password?' on the sign-in screen.")
    elif cmd == "role" and len(args) == 3:
        user = auth.get_user_by_email(args[1])
        auth.set_custom_user_claims(user.uid, {"role": need_role(args[2])})
        auth.revoke_refresh_tokens(user.uid)  # force a fresh sign-in so the new role applies now
        print(f"{args[1]} is now {args[2]} (they will be asked to sign in again)")
    elif cmd == "list":
        for user in auth.list_users().iterate_all():
            role = (user.custom_claims or {}).get("role", "employee")
            state = "disabled" if user.disabled else "active"
            print(f"{user.email:<40} {role:<10} {state}")
    elif cmd in ("disable", "enable") and len(args) == 2:
        user = auth.get_user_by_email(args[1])
        auth.update_user(user.uid, disabled=(cmd == "disable"))
        if cmd == "disable":
            auth.revoke_refresh_tokens(user.uid)
        print(f"{args[1]} {cmd}d")
    elif cmd == "delete" and len(args) == 2:
        user = auth.get_user_by_email(args[1])
        auth.delete_user(user.uid)
        print(f"Deleted {args[1]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])

# Security — Al-Noor HR Assistant

How the assistant protects company data, and how to check it. Run `python eval/security_test.py <site-url>`
after every deploy.

## Who can see what

| Data | Employee | HR admin | Anyone on the internet |
|---|---|---|---|
| General company policies | ✅ through answers | ✅ | ❌ |
| Confidential policies (salaries, bonus, disciplinary) | ❌ never searched | ✅ | ❌ |
| Saudi Labor Law (public) | ✅ | ✅ | ❌ (needs sign-in) |
| Documents page (upload / delete) | ❌ 403 | ✅ | ❌ 401 |
| Analytics dashboard | ❌ 403 | ✅ | ❌ 401 |
| Raw files in Cloud Storage | ❌ | ❌ (only via the app) | ❌ |
| Question records in Firestore | ❌ | ❌ (only totals on the dashboard) | ❌ |

## Protections in place

**Sign-in and roles**
- Google Identity Platform, email and password; public sign-up is turned off (HR creates accounts).
- Every API request carries a signed ID token, verified on the server. The role (`employee` / `hr_admin`)
  is a custom claim set only by an administrator — users cannot change it.
- Revoked or disabled accounts stop working immediately (`check_revoked`), not when the token expires.
- Access control happens in the backend: an employee's question is never searched against the
  confidential index, so the model cannot leak what it never receives.

**The AI**
- Answers only from retrieved sources; otherwise a fixed "contact HR" reply.
- Source text is treated as data, not instructions (prompt-injection rule); injection attempts are tested.
- Quotes shown to users are verified word-for-word against the source.

**The web app**
- Content-Security-Policy: only our scripts, the Firebase sign-in library and one hashed inline script
  may run; the page cannot be framed (clickjacking); forms cannot post elsewhere.
- HSTS (HTTPS only), `nosniff`, strict referrer policy, no caching of API responses.
- Interactive API docs are switched off in production.
- Rate limit: 20 questions per minute per user.
- Uploads: allowed types only, 10 MB limit, and the file's first bytes must match its type.

**Google Cloud**
- The service runs as a dedicated service account with only the roles it needs; no downloadable keys.
- Buckets: uniform access and public access prevention (no file can be made public by mistake).
- Firestore is used only by the backend; direct access from the internet is refused.
- The browser API key is restricted to the sign-in APIs and to the site's own address.
- Question records are anonymous (no name or email) and deleted automatically after 180 days (Firestore TTL).
- Logs contain metadata only (role, language, timing) — never questions, answers or emails.

## Checklist before handing over to a client
- [ ] `python eval/security_test.py <url>` — all ok
- [ ] `python eval/roles_test.py` — 12/12, no `CONF-` source for employees
- [ ] Only real HR staff have the `hr_admin` role (`python infra/users.py list`)
- [ ] Test accounts disabled or deleted
- [ ] `AUTH_DISABLED` is NOT set on Cloud Run
- [ ] Billing budget alert set (Day 14)

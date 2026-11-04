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

## Client isolation (one Google Cloud project per client)
Each client company gets its **own Google Cloud project**: its own sign-in users, search indexes, storage,
database and billing. Nothing is shared between clients except the code, so one client's documents or users
can never appear for another — isolation is enforced by Google's project boundary, not by our code.
- The sign-in token is only accepted if it was issued for this project (checked on every request).
- The company name is a setting (`COMPANY_NAME_EN`, `COMPANY_NAME_AR`), so the same code is deployed for each client.
- The public Saudi Labor Law index is the one part that can be rebuilt identically in every client project.

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
- Employees can download everything held about them ("Your data" link → `GET /me/data`).

**Auto-sync service (`hr-ingest`, Day 12B)**
- Private: only the Eventarc triggers and the nightly scheduler (signed in as the service account) can call it;
  anyone else gets 403. It has no web page and no API docs.
- It reads the raw bucket and writes only to the processed bucket and the search indexes.

**Guardrails (tested in `eval/guardrail_test.py`)**
- Off-topic questions, invented article numbers and general-knowledge questions get the fixed "contact HR"
  reply — enforced in code (no cited source → fixed reply), not only by the prompt.
- A policy document containing hidden instructions ("ignore previous instructions…") cannot change the
  assistant's behaviour: source text is treated as data.

## Checklist before handing over to a client
- [ ] `python eval/security_test.py <url>` — all ok
- [ ] `python eval/roles_test.py` — 12/12, no `CONF-` source for employees
- [ ] `python eval/guardrail_test.py` — all ok, then delete the EN-99 test document
- [ ] Only real HR staff have the `hr_admin` role (`python infra/users.py list`)
- [ ] Test accounts disabled or deleted
- [ ] `AUTH_DISABLED` is NOT set on Cloud Run
- [ ] Billing budget alert set (Day 14)

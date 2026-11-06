# Build log - HR Assistant

## Day 2 - Arabic OCR ingestion (Document AI, EU region)
- 15 documents processed (12 policies + 3 confidential); 3 Arabic policies tested as noisy, tilted scans.
- OCR accuracy on scans vs clean originals: 98.1%, 97.9%, 89.7% (average 95.2%); all numbers correct.
- Lowest score: the most tilted scan (2 degrees). Lesson: ask clients for straight 300 dpi scans.
- Problem: "Processor not found" - processor was created in the wrong GCP project. Fix: recreated it in hr-assistent-511809.

## Day 3 - Vertex AI Search index
- Data store company-policies (global): 12 policies, layout parser, 500-token chunks with ancestor headings.
- Search app hr-assistant connected to it; confidential docs kept out of this index.
- Retrieval test, 27 questions, hit@3: 78% at default relevance threshold -> 93% at LOWEST (AR 100%, EN 88%).
- At default strictness every miss was "no results" (filtered out), never a wrong policy.
- Remaining misses: English questions about Arabic-only policies (Hajj leave, late arrivals). Fix planned for Day 7: bilingual keywords per document.
- Lesson: console created the data store in global despite choosing eu; app and data store must share one location. Verify with the API.

## Day 4 - RAG core (Gemini + Vertex AI Search)
- Model: gemini-3.8-flash (chosen with check_models.py; kept in .env so it can change per client).
- First version used Gemini's built-in grounding: only 6/27 answered, because its search uses
  Google's default relevance filter, which can't be changed.
- Rewrote as two-step RAG: our code searches (relevance LOWEST, 6 chunks with neighbours),
  then Gemini answers only from those numbered sources and returns which ones it used (JSON).
- Smoke test, 35 questions: answered with the correct source 27/27 (100%); correctly deferred 8/8 (100%).
- Cross-language works both ways (Arabic question <- English policy and vice versa).
- Trust rule in code: no cited source -> fixed "please contact HR" reply; no search results -> Gemini not called.
- Gap noted: answers use one policy even when a related fact sits in another (remote work + Ramadan).

## Day 5 - API on Cloud Run
- FastAPI service: GET /health, POST /ask (input validation, 20 req/min rate limit, safe 503 errors,
  logs metadata only - never question text).
- Containerised with a Dockerfile (python:3.12-slim, non-root user); built by Cloud Build on deploy.
- Cloud Run service hr-api: private (IAM-only), min 0 / max 2 instances, runs as hr-assistant-sa
  with least-privilege roles (aiplatform.user, discoveryengine.viewer).
- Verified: /health and /ask work with an identity token; 403 without one.
- Final Day 6 config: gemini-2.5-flash, thinking MEDIUM, explicit answer language.
  Smoke test: 27/27 answered with correct source AND same language; 8/8 correct refusals; ~3 s median.

## Day 7 - Bilingual polish and verified citations
- Verified quotes: Gemini returns an exact quote per source; code accepts it only if it appears in the
  source (normalising Arabic diacritics/tatweel). Result: 28/28 citations verified.
- Bilingual policy titles (doc_titles.json); UI shows policy names in the page language.
- Yes/no rule: fixed "Do I need a report?" -> now "No, one day without a report is allowed twice a year".
- Bilingual pairs test (same 12 questions in EN + AR) found 1 gap: English "absent" missed the Arabic
  Attendance policy. Fix: bilingual search (translate with gemini-2.5-flash-lite, search both languages in
  parallel, merge). Pairs 11/12 -> 12/12. Bonus: remote-work answer now includes the Ramadan rule
  from a second (Arabic) policy.
- Smoke test: 27/27 answered (source + language), 8/8 refusals. Latency 3.7 s median (+0.8 s).
- Open for Day 13: "only with conditions" answers start with a bare Yes/No (#6, #11).

## Day 8 - Sign-in and roles
- Google Identity Platform (email/password); public sign-up disabled; accounts created by admin script
  (infra/users.py) with a role claim: employee | hr_admin.
- Backend verifies the ID token on every request; role read from the signed token only
  (role sent in the request is ignored; unknown role -> employee).
- Confidential HR files in a separate index (hr-confidential); employees' searches can't reach it.
  Employees get the same "contact HR" reply, so restricted documents aren't revealed.
- roles_test: ../12 checks passed (employee refused + admin answered for 4 confidential questions).
- Access code removed; /ask returns 401 without sign-in.

## Day 9 - Document admin page
- HR admins upload PDF/scan/image/text with EN+AR titles and audience (all employees / HR only);
  backend runs OCR, stores raw + text in Cloud Storage, imports into the matching index (incremental).
- Firestore "documents" collection: title, audience, status (indexing/ready/failed/deleted),
  who uploaded/deleted and when (audit trail, no content). Existing 15 docs registered by seed script.
- Delete removes the document from the index and storage; the assistant stops answering from it.
- Admin API returns 403 for employees, 401 without sign-in. Admin page hidden for employees.
- Tested live: new Arabic policy uploaded -> Ready in .. min -> answered with verified quote -> deleted -> contact HR.

## Day 10 — Analytics dashboard
- Every question is recorded anonymously in Firestore (no name or email), kept 180 days.
- Dashboard for HR admins: answer rate, questions per day, questions the policies don't answer (policy gaps),
  most-used policies, questions by department. Arabic/English, light/dark, phone-friendly, table view.
- Department added to each user's profile (`infra/users.py department`).
- Demo data script (`eval/seed_analytics.py`), flagged and removable with `--delete`.
- Security: employees get 403 on /admin/analytics, no sign-in gets 401.

## Day 11 — Saudi Labor Law layer
- Official Labor Law (with 2025 amendments) in its own search index, available to every role.
- Company policy first; the law fills gaps (end of service, sick pay, deductions) and is cited by article.
- Detects policies below the legal minimum: outdated 10-week maternity leave (law: 12) and a 5-day
  disciplinary appeal window (law: 30 days). Shown on the HR dashboard.
- Problem: Gemini read "Article 151" as "51" → article numbers only from the full heading, otherwise none.
- Results: roles 12/12, smoke 27/27 + 8/8, law 9/9, conflict 2/2.

## Day 12 — Security hardening
- Security headers (CSP with hashed inline script, HSTS, no framing); API docs off in production.
- Disabled accounts / changed roles take effect immediately (token revocation check).
- Upload content check (file signature must match its type).
- Firestore TTL deletes question records after 180 days; buckets locked against public access.
- Browser API key restricted to sign-in APIs and the site's address; least-privilege service account
  (removed duplicate and unused roles, storage access limited to the two buckets).
- Results: security test 25/25 (headers, auth, data exposure, 5 prompt-injection attacks); roles 12/12.

## Day 12B — Auto-sync ingestion
- The raw bucket is the source of truth: Eventarc triggers + private hr-ingest service (same code, sync:app)
  index any file added, replaced, moved or deleted — portal or not — within minutes.
- Nightly reconcile (02:00 Riyadh) repairs missed events; dry-run mode and a mass-deletion safety limit.
- Existing 17 documents (incl. the law) adopted without re-indexing. Portal gained Replace + failure reasons.
- Problems: Cloud Storage and Eventarc service agents weren't provisioned → created with
  `gcloud beta services identity create`; browser key blocked the second Cloud Run URL → both URLs allowed.
- Demo: gym policy dropped into the folder → cited answer; file removed → "contact HR".

## Day 13 — Evaluation with an AI judge
- 50-question test set (18 Arabic, 32 English; policy, Labor Law, conflict, conditional, refusal, role).
- AI judge grades every answer; also checks citations, leaks, language, misleading Yes/No, consistency, cost.
- Fixes: conditional answers no longer start with a bare Yes/No; temperature 0 for consistency;
  "answer the question asked" + bonus vs end-of-service terminology (Arabic مكافأة); Arabic file names.
- Model is a setting: Gemini (default) or Claude on Google Cloud (RAG_MODEL).
- Results: 98% correct, 100% correct sources, 0 leaks, 96% consistent, 4.5 s median, ~$7 per 1,000 questions.

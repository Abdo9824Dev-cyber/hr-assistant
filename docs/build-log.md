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

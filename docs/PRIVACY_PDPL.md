# Privacy notes — Saudi Personal Data Protection Law (PDPL)

> These are technical notes to support the client's compliance work, not legal advice.
> The client (the employer) is the data **controller**; the final assessment belongs to their legal or DPO team.

## Background
- The PDPL came into force on 14 September 2023 and has been fully enforceable since 14 September 2024.
- Regulator: the Saudi Data and Artificial Intelligence Authority (SDAIA).
- Breaches that may cause harm must be reported to SDAIA within 72 hours, and affected people informed without delay.
- Transfers of personal data outside the Kingdom are allowed only under the Transfer Regulation
  (adequate countries or approved safeguards such as standard contractual clauses, plus a risk assessment in some cases).
  Check SDAIA's current guidance, as these rules are still being updated.

## What personal data the assistant handles

| Data | Where | Personal? | Kept for |
|---|---|---|---|
| Employee accounts (email, role, department) | Identity Platform | Yes | Until HR deletes the account |
| Questions employees type | Sent to Gemini to answer; stored anonymously in Firestore `chats` | Possibly — an employee may type personal details | 180 days, then deleted automatically |
| Question records (question text, language, department, timing) | Firestore `chats` | No name or email; department only | 180 days (TTL on `expire_at`) |
| Company policies (may name managers) | Cloud Storage + Vertex AI Search | Low | Until HR deletes them |
| Admin actions (who uploaded / deleted a document) | Firestore `documents` | Yes (admin email) | Until the document record is removed |
| Service logs | Cloud Logging | No (metadata only) | Cloud Logging default (30 days) |

Not collected: names in question records, chat history per person, IP addresses in our records, cookies for tracking.

## Data location — fill in for each client
Check each with the commands shown, and record the answers here:

| Service | Region | Command to check |
|---|---|---|
| Cloud Run (the app) | me-central1 (Doha, Qatar) | `REGION` in `.env` |
| Cloud Storage buckets | … | `gcloud storage buckets describe gs://$PROJECT_ID-raw-docs --format='value(location)'` |
| Firestore | … | `gcloud firestore databases describe --format='value(locationId)'` |
| Document AI (OCR) | eu | processor location in `.env` (`DOCAI_LOCATION`) |
| Vertex AI Search | global | `SEARCH_LOCATION` in `.env` |
| Gemini | global endpoint | `GEMINI_LOCATION` in `.env` |

**Important for Saudi clients:** in this demo every service runs outside the Kingdom — the app in Doha (me-central1),
OCR in the EU, search and the model on Google's global endpoints.
For a client whose data must stay in Saudi Arabia, plan a deployment using Google Cloud's Dammam region
(me-central2) where each service is available there, or document the transfer under the Transfer Regulation.
Discuss this with the client before go-live — it affects which services and models can be used.

## Employee rights (how to handle requests)
- **Access:** each employee can download their data with the **"Your data"** link under the chat box
  (`GET /me/data`: account details, plus an explanation that questions are anonymous and not stored per person).
- **Correction of account data:** HR updates it with `infra/users.py`.
- **Deletion:** delete the account (`infra/users.py delete <email>`). There is no per-person chat history to
  delete: conversations live only in the browser tab, and question records hold no identity (they cannot be
  linked back to a person) and expire after 180 days. Privacy by design: we avoid storing what we would
  otherwise have to delete.
- **Information:** show employees a short notice on the chat page (the empty screen already states that
  answers come from company policies; add the client's privacy notice link there).

## If something goes wrong (breach procedure)
1. Disable affected accounts (`infra/users.py disable`) and, if needed, take the site offline:
   `gcloud run services remove-iam-policy-binding hr-api --region $REGION --member=allUsers --role=roles/run.invoker`
   (undo later with `add-iam-policy-binding` and the same options).
2. Find out what was exposed (Cloud Logging, Firestore, Storage access logs).
3. The client's DPO decides on notifying SDAIA (within 72 hours) and the affected employees.
4. Fix, test with `eval/security_test.py`, redeploy, and write a short incident note.

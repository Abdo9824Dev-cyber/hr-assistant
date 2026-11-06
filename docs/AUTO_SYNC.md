# Auto-sync (Day 12B)

The raw bucket `gs://<project>-raw-docs` is the single source of truth. The folder decides who can use a file:

| Folder | Search index | Who gets answers from it |
|---|---|---|
| `policies/` | company policies | all employees |
| `confidential/` | confidential | HR admins only |
| `law/` | Saudi Labor Law (PDF, layout parser) | everyone |

Other folders and sub-folders are ignored.

## What happens when…

| Action in the bucket | Result |
|---|---|
| A file is added (portal, Console, `gcloud storage cp`, a sync job) | OCR + indexed within minutes |
| A file is replaced with the same name | Updated in place (old version removed from the index) |
| A file is deleted | Removed from the index; record kept as `deleted` (audit trail) |
| A file is moved to another folder | Removed from the old index, added to the new one |
| An event is lost or processing fails | The nightly reconcile (02:00 Riyadh) repairs it |

The system never decides that a policy is outdated: a person deletes, moves or replaces the file.

## How it works
- `hr-ingest` — a **private** Cloud Run service (same code as the app, entry point `sync:app`).
- Eventarc triggers: `object.finalized` → `/ingest`, `object.deleted` → `/delete`.
- Cloud Scheduler `hr-reconcile` → `/reconcile` every night.
- Portal uploads are tagged `source=portal` on the file and handled by the portal (instant feedback for HR);
  the sync service only steps in if the portal didn't finish.

## Safety rules
- Repeated events for the same file version are ignored (no double OCR cost).
- A delete event for a file that still exists is an overwrite, not a delete.
- Reconcile never removes more than `SYNC_MAX_REMOVALS` (default 3) documents in one run, and stops if the
  bucket looks empty. It can always be run as a dry run first:
  `python backend/sync.py reconcile --dry-run`
- Text is written only to the processed bucket, never to the raw bucket (no event loops).

## Google Drive (Day 12C)
HR can keep policies in Google Drive instead of uploading them. Every 15 minutes (`hr-drive-sync` job →
`hr-ingest /drive-sync`) the shared Drive folder is mirrored into the raw bucket, and auto-sync does the rest.

| Drive sub-folder | Bucket folder |
|---|---|
| `Policies` (or `السياسات`) | `policies/` |
| `HR Confidential` / `Confidential` (or `سري`) | `confidential/` |
| `Labor Law` / `Law` (or `نظام العمل`) | `law/` (PDF only) |

- Supported: PDF, PNG, JPG, TIFF, TXT, and **Google Docs** (exported as PDF). Word files: save as PDF first.
- Edited in Drive → updated. Deleted, renamed or moved → the old copy is removed.
- English title = file name; Arabic title = the file's Drive **description** (if it contains Arabic).
- Read-only access: the folder is shared with the service account as **Viewer**. Nothing in Drive is changed.
- Safety: only files that came from Drive are ever replaced or removed in the bucket; portal uploads are never
  touched. If Drive returns no files (e.g. the folder was unshared), nothing is removed.
- Test without changing anything: `POST /drive-sync?dry_run=1`.

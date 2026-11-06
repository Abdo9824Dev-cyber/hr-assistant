"""Day 12B: auto-sync - the raw bucket is the single source of truth.

Any file added, replaced, moved or deleted in gs://<project>-raw-docs/{policies,confidential,law}/ is reflected
in the search index within minutes, however it got there (portal, Cloud Console, gcloud, a sync job).
A nightly reconcile repairs anything an event missed.

Runs as a PRIVATE Cloud Run service "hr-ingest" (same code and image as the app, different entry point):
    POST /ingest      Eventarc: google.cloud.storage.object.v1.finalized  (file created or overwritten)
    POST /delete      Eventarc: google.cloud.storage.object.v1.deleted    (file deleted, moved, or overwritten)
    POST /reconcile   Cloud Scheduler, nightly   (?dry_run=1 only reports the plan)
    POST /drive-sync  Cloud Scheduler, every 15 min: Google Drive folder -> raw bucket (Day 12C, drive_sync.py)

Safety rules (nothing that exists today is destroyed):
  - Portal uploads (file metadata source=portal) are left to the portal - no double OCR.
  - Repeated events for the same file version (generation) are ignored - no double OCR bill.
  - A delete event for a file that still exists is an overwrite - the document is updated, not removed.
  - Existing documents are ADOPTED (their version is recorded) - nothing is re-indexed.
  - Reconcile never removes more than a few documents at once, and does nothing if the bucket looks empty.
  - Text goes only to the processed bucket - never back into the raw bucket (no event loops).

Also a command line tool (from the project root, with .venv and .env loaded):
    python backend/sync.py reconcile --dry-run     # show what would change, change nothing
    python backend/sync.py reconcile               # apply
"""
import logging
import os
import re
import sys
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from google.cloud import firestore

import ingest

log = logging.getLogger("hr-ingest")
logging.basicConfig(level=logging.INFO)

COLLECTION = os.environ.get("DOCS_COLLECTION", "documents")
STORES = ("policies", "confidential", "law")
LAW_TYPES = (".pdf",)
MAX_REMOVALS = int(os.environ.get("SYNC_MAX_REMOVALS", "3"))   # more than this in one run = stop and ask a human
_db = None


def db():
    global _db
    if _db is None:
        _db = firestore.Client(project=ingest.PROJECT)
    return _db


def now():
    return datetime.now(timezone.utc)


def parse(path: str):
    """'policies/EN-01_Annual_Leave_Policy.pdf' -> ('policies', 'EN-01_Annual_Leave_Policy', '.pdf'), else None."""
    if "/" not in path or path.endswith("/"):
        return None
    store = path.split("/", 1)[0]
    ext = ingest.extension(path)
    if store not in STORES or path.count("/") != 1:
        return None                                  # other folders and sub-folders are ignored
    if ext not in (LAW_TYPES if store == "law" else ingest.MIME):
        return None
    return store, ingest.safe_name(path), ext


def default_titles(name: str) -> dict:
    """'EN-07_Maternity_Leave_Policy' -> 'Maternity Leave Policy' (HR can rename it later with Replace)."""
    title = re.sub(r"^(CONF-|LAW-)?(EN|AR)(-\d+)?_", "", name).replace("_", " ").strip() or name
    return {"title_en": title, "title_ar": title}


# ---------------------------------------------------------------- one file
def ingest_file(path: str, generation: str, force: bool = False) -> str:
    parsed = parse(path)
    if not parsed:
        return "skipped"
    store, name, _ = parsed
    raw_uri = f"gs://{ingest.RAW_BUCKET}/{path}"
    blob = ingest._client("gcs").bucket(ingest.RAW_BUCKET).get_blob(path)
    if blob is None:
        return "gone"                                # deleted again before we got here
    generation = str(blob.generation)
    meta = blob.metadata or {}
    ref = db().collection(COLLECTION).document(name)
    rec = (ref.get().to_dict() or {})
    active = rec and rec.get("status") != "deleted"

    if active and rec.get("gcs_raw") and rec["gcs_raw"] != raw_uri:
        log.warning("name clash: %s and %s map to the same document %s - skipped", raw_uri, rec["gcs_raw"], name)
        return "clash"
    if not force and meta.get("source") == "portal":
        return "portal"                              # the portal already did the work
    if not force and active and rec.get("generation") == generation and rec.get("status") in ("indexing", "ready"):
        return "duplicate"                           # repeated event: no second OCR bill

    titles = {k: meta.get(k) or rec.get(k) or default_titles(name)[k] for k in ("title_en", "title_ar")}
    base = {"store": store, "gcs_raw": raw_uri, "generation": generation, "source": "sync",
            "uploaded_by": rec.get("uploaded_by") or meta.get("uploaded_by") or "folder sync",
            "updated_at": now(), **titles}
    if not rec.get("created_at"):
        base["created_at"] = now()
    try:
        if store == "law":                           # the law: Google's layout parser reads the PDF itself
            if active or raw_uri in ingest.indexed_uris("law"):
                ingest.remove_from_index("law", raw_uri)
            operation = ingest.start_import_uri("law", raw_uri)
            ref.set({**base, "gcs_text": "", "status": "indexing", "operation": operation, "error": ""}, merge=True)
            return "indexing"
        data = blob.download_as_bytes()
        text = ingest.extract_text(data, path)
        if len(text) < 20:
            raise ingest.IngestError("No readable text was found. Check the scan quality.")
        if active:                                   # replaced file: take the old version out first
            ingest.remove_from_index(rec.get("store", store), rec.get("gcs_text", ""))
        gcs_text = ingest.save_text(store, name, text)
        operation = ingest.start_import(store, gcs_text)
        ref.set({**base, "gcs_text": gcs_text, "chars": len(text), "status": "indexing",
                 "operation": operation, "error": ""}, merge=True)
        log.info("synced %s -> %s (%d chars)", path, store, len(text))
        return "indexing"
    except ingest.IngestError as e:
        ref.set({**base, "status": "failed", "error": str(e)[:300]}, merge=True)
        return "failed"
    except Exception as e:                           # reconcile retries it tonight
        log.exception("sync failed for %s", path)
        ref.set({**base, "status": "failed", "error": f"Processing error: {str(e)[:200]}"}, merge=True)
        return "failed"


def remove_file(path: str) -> str:
    parsed = parse(path)
    if not parsed:
        return "skipped"
    store, name, _ = parsed
    if ingest._client("gcs").bucket(ingest.RAW_BUCKET).get_blob(path) is not None:
        return "overwrite"                           # replaced, not deleted: /ingest updates it
    raw_uri = f"gs://{ingest.RAW_BUCKET}/{path}"
    ref = db().collection(COLLECTION).document(name)
    rec = ref.get().to_dict() or {}
    if not rec or rec.get("status") == "deleted":
        return "not-indexed"
    if rec.get("gcs_raw") and rec["gcs_raw"] != raw_uri:
        return "other-file"                          # the record belongs to a different original
    ingest.remove_from_index(rec.get("store", store), rec.get("gcs_text") or raw_uri)
    if rec.get("gcs_text"):
        ingest.delete_files(rec["gcs_text"])         # processed text only; the raw file is already gone
    ref.set({"status": "deleted", "deleted_by": rec.get("deleted_by") or "folder sync",
             "updated_at": now(), "operation": ""}, merge=True)
    log.info("removed %s from the index", path)
    return "deleted"


# ---------------------------------------------------------------- nightly repair
def reconcile(dry_run: bool = False) -> dict:
    gcs = ingest._client("gcs")
    live = {}
    for store in STORES:
        for b in gcs.list_blobs(ingest.RAW_BUCKET, prefix=f"{store}/"):
            if parse(b.name):
                live[b.name] = str(b.generation)
    records = {s.id: (s.to_dict() or {}) for s in db().collection(COLLECTION).stream()}
    plan = {"adopt": [], "ingest": [], "remove": [], "clash": [], "refresh": [], "warnings": []}
    if not live:
        plan["warnings"].append("The raw bucket has no documents - nothing was changed (safety stop).")
        return plan

    law_index = None
    seen = {}
    for path, gen in sorted(live.items()):
        store, name, _ = parse(path)
        uri = f"gs://{ingest.RAW_BUCKET}/{path}"
        if name in seen:
            plan["clash"].append(f"{path} (same document name as {seen[name]})")
            continue
        seen[name] = path
        rec = records.get(name, {})
        active = rec and rec.get("status") != "deleted"
        if active and rec.get("gcs_raw") and rec["gcs_raw"] != uri:
            plan["clash"].append(f"{path} (document {name} belongs to {rec['gcs_raw']})")
        elif active and rec.get("status") == "ready" and not rec.get("generation"):
            plan["adopt"].append(path)                # built before Day 12B: record its version, change nothing
        elif not rec and store == "law":
            if law_index is None:
                law_index = ingest.indexed_uris("law")
            (plan["adopt"] if uri in law_index else plan["ingest"]).append(path)
        elif active and rec.get("generation") == gen and rec.get("status") in ("ready", "indexing"):
            if rec.get("status") == "indexing":
                plan["refresh"].append(name)
        else:
            plan["ingest"].append(path)               # new, changed or failed

    live_uris = {f"gs://{ingest.RAW_BUCKET}/{p}" for p in live}
    for name, rec in records.items():
        if rec.get("status") != "deleted" and rec.get("gcs_raw") and rec["gcs_raw"] not in live_uris:
            plan["remove"].append(rec["gcs_raw"].split("/", 3)[3])
    if len(plan["remove"]) > MAX_REMOVALS:
        plan["warnings"].append(f"{len(plan['remove'])} documents would be removed - more than the safety limit "
                                f"({MAX_REMOVALS}). Nothing was removed. Check the bucket, then raise SYNC_MAX_REMOVALS.")
        plan["remove_blocked"], plan["remove"] = plan["remove"], []

    if dry_run:
        return plan

    for path in plan["adopt"]:
        store, name, _ = parse(path)
        rec = records.get(name, {})
        update = {"generation": live[path], "gcs_raw": f"gs://{ingest.RAW_BUCKET}/{path}"}
        if not rec:                                   # the law imported on Day 11
            update.update({"store": store, "status": "ready", "gcs_text": "", "source": "sync",
                           "uploaded_by": "initial import", "created_at": now(), "updated_at": now(),
                           **default_titles(name)})
        db().collection(COLLECTION).document(name).set(update, merge=True)
    plan["results"] = {path: ingest_file(path, live[path], force=True) for path in plan["ingest"]}
    for path in plan["remove"]:
        plan["results"][path] = remove_file(path)
    for name in plan["refresh"]:
        try:
            status = ingest.import_status(records[name].get("operation", ""))
            if status != "indexing":
                db().collection(COLLECTION).document(name).set({"status": status, "updated_at": now()}, merge=True)
        except Exception:
            pass
    return plan


# ---------------------------------------------------------------- web layer (private service)
app = FastAPI(title="hr-ingest", docs_url=None, redoc_url=None, openapi_url=None)


@app.post("/ingest")
async def on_finalized(request: Request):
    obj = await request.json()                       # Cloud Storage object metadata (CloudEvent data)
    result = ingest_file(obj.get("name", ""), str(obj.get("generation", "")))
    log.info("event finalized %s -> %s", obj.get("name"), result)
    return {"result": result}


@app.post("/delete")
async def on_deleted(request: Request):
    obj = await request.json()
    result = remove_file(obj.get("name", ""))
    log.info("event deleted %s -> %s", obj.get("name"), result)
    return {"result": result}


@app.post("/reconcile")
def nightly(dry_run: int = 0):
    plan = reconcile(dry_run=bool(dry_run))
    log.info("reconcile dry_run=%s adopt=%d ingest=%d remove=%d clash=%d warnings=%s", bool(dry_run),
             len(plan["adopt"]), len(plan["ingest"]), len(plan["remove"]), len(plan["clash"]), plan["warnings"])
    return plan


@app.post("/drive-sync")
def drive_sync_route(dry_run: int = 0):
    import drive_sync
    plan = drive_sync.sync(dry_run=bool(dry_run))
    return plan


@app.get("/health")
def health():
    return {"ok": True}


def _print(plan: dict, dry_run: bool) -> None:
    print("DRY RUN - nothing was changed\n" if dry_run else "Applied:\n")
    labels = {"adopt": "already indexed, version recorded (no re-indexing)", "ingest": "to OCR and index",
              "remove": "to remove from the index (file no longer in the bucket)", "clash": "skipped: name clash",
              "refresh": "still indexing", "remove_blocked": "NOT removed (safety limit)"}
    for key, label in labels.items():
        items = plan.get(key) or []
        print(f"{label}: {len(items)}")
        for item in items:
            result = (plan.get("results") or {}).get(item)
            print(f"   - {item}" + (f"  -> {result}" if result else ""))
    for w in plan["warnings"]:
        print("WARNING:", w)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "reconcile":
        sys.exit(__doc__)
    dry = "--dry-run" in sys.argv
    _print(reconcile(dry_run=dry), dry)

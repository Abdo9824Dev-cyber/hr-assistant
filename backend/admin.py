"""Day 9: document admin API (HR admins only).

    GET    /admin/documents          list documents (refreshes "indexing" ones)
    POST   /admin/documents          upload: file + store + English/Arabic titles
    DELETE /admin/documents/{id}     remove from search, storage, and mark as deleted

Every document has a record in Firestore, collection "documents" (id = file name without extension):
    title_en, title_ar, store, status (indexing | ready | failed | deleted), gcs_raw, gcs_text,
    operation, chars, uploaded_by, created_at, updated_at, deleted_by
"""
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from google.cloud import firestore

import ingest
from auth import require_hr_admin

log = logging.getLogger("hr-api")
router = APIRouter(prefix="/admin", tags=["admin"])
COLLECTION = os.environ.get("DOCS_COLLECTION", "documents")
STORES = ("policies", "confidential")
_db = None


def db():
    global _db
    if _db is None:
        _db = firestore.Client(project=ingest.PROJECT)
    return _db


def now():
    return datetime.now(timezone.utc)


def public(doc_id: str, d: dict) -> dict:
    """The fields the admin page shows (no internal storage paths)."""
    updated = d.get("updated_at")
    return {
        "id": doc_id,
        "title_en": d.get("title_en", doc_id),
        "title_ar": d.get("title_ar", doc_id),
        "store": d.get("store", "policies"),
        "status": d.get("status", "ready"),
        "chars": d.get("chars", 0),
        "uploaded_by": d.get("uploaded_by", ""),
        "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else None,
    }


@router.get("/documents")
def list_documents(user: dict = Depends(require_hr_admin)):
    out = []
    for snap in db().collection(COLLECTION).stream():
        d = snap.to_dict() or {}
        if d.get("status") == "deleted":
            continue
        if d.get("status") == "indexing":
            try:
                status = ingest.import_status(d.get("operation", ""))
            except Exception:
                status = "indexing"  # couldn't check right now; try again on the next refresh
            if status != "indexing":
                snap.reference.update({"status": status, "updated_at": now()})
                d["status"] = status
        out.append(public(snap.id, d))
    out.sort(key=lambda x: (x["store"], x["title_en"].lower()))
    return {"documents": out}


@router.post("/documents", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    store: str = Form(...),
    title_en: str = Form(..., min_length=2, max_length=120),
    title_ar: str = Form(..., min_length=2, max_length=120),
    user: dict = Depends(require_hr_admin),
):
    if store not in STORES:
        raise HTTPException(422, "Choose who can see the document: all employees or HR only.")
    name = ingest.safe_name(file.filename or "document")
    ref = db().collection(COLLECTION).document(name)
    existing = ref.get()
    if existing.exists and (existing.to_dict() or {}).get("status") != "deleted":
        raise HTTPException(409, "A document with this file name already exists. "
                                 "Delete it first to replace it, or rename the file.")

    data = await file.read(ingest.MAX_BYTES + 1)
    try:
        text = ingest.extract_text(data, file.filename or "")
        if len(text) < 20:
            raise ingest.IngestError("No readable text was found. Check the scan quality and try again.")
        paths = ingest.save_files(store, name, file.filename or "", data, text)
        operation = ingest.start_import(store, paths["gcs_text"])
    except ingest.IngestError as e:
        raise HTTPException(422, str(e))
    except Exception:
        log.exception("upload failed")
        raise HTTPException(502, "The upload couldn't be processed right now. Try again in a minute.")

    record = {
        "title_en": title_en.strip(), "title_ar": title_ar.strip(), "store": store,
        "status": "indexing", "operation": operation, "chars": len(text),
        "uploaded_by": user["email"], "created_at": now(), "updated_at": now(),
        **paths,
    }
    ref.set(record)
    log.info("document uploaded id=%s store=%s chars=%d", name, store, len(text))  # no content in logs
    return public(name, record)


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, user: dict = Depends(require_hr_admin)):
    ref = db().collection(COLLECTION).document(doc_id)
    snap = ref.get()
    if not snap.exists or (snap.to_dict() or {}).get("status") == "deleted":
        raise HTTPException(404, "That document doesn't exist or was already deleted.")
    d = snap.to_dict() or {}
    try:
        ingest.remove_from_index(d.get("store", "policies"), d.get("gcs_text", ""))
        ingest.delete_files(d.get("gcs_text", ""), d.get("gcs_raw", ""))
    except Exception:
        log.exception("delete failed")
        raise HTTPException(502, "The document couldn't be deleted right now. Try again in a minute.")
    # Keep a small record of what was deleted, when and by whom (audit trail), without the content.
    ref.update({"status": "deleted", "deleted_by": user["email"], "updated_at": now(), "operation": ""})
    log.info("document deleted id=%s", doc_id)
    return {"deleted": doc_id}

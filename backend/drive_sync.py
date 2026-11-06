"""Day 12C: Google Drive -> raw bucket. Day 12B auto-sync then does OCR and indexing.

HR keeps working in Google Drive. One shared folder holds three sub-folders:
    Policies          -> raw-docs/policies/       (all employees)      also accepted: "السياسات"
    HR Confidential   -> raw-docs/confidential/   (HR admins only)     also: "Confidential", "سري"
    Labor Law         -> raw-docs/law/            (Saudi Labor Law)    also: "Law", "نظام العمل"
The folder is shared (Viewer) with the app's service account e-mail. Read-only: we never change Drive.

Every 15 minutes (Cloud Scheduler -> hr-ingest /drive-sync):
  - new or edited file in Drive   -> copied to the bucket (Google Docs exported as PDF)
  - file deleted / moved in Drive -> removed from the bucket (auto-sync then removes it from the index)
Safety: only bucket files that came from Drive (metadata source=drive) are ever replaced or removed;
portal uploads and manual files are never touched. Mass removals and an empty Drive listing stop the run.

Titles: an English file name is the English title, and the Arabic title goes in the file's Drive "description"
(right-click > File information > Details). An Arabic file name works too: it becomes the Arabic title, and the
description (in English) becomes the English title. Without a description the name is used for both.
"""
import logging
import os
import re

import google.auth
from google.auth.transport.requests import AuthorizedSession

import ingest

log = logging.getLogger("hr-ingest")
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")
MAX_REMOVALS = int(os.environ.get("SYNC_MAX_REMOVALS", "3"))
API = "https://www.googleapis.com/drive/v3/files"
FOLDER = "application/vnd.google-apps.folder"
SUBFOLDERS = {
    "policies": "policies", "السياسات": "policies",
    "hr confidential": "confidential", "confidential": "confidential", "سري": "confidential",
    "labor law": "law", "law": "law", "نظام العمل": "law",
}
# Drive file type -> (bucket extension, export as)    export=None means download the file as it is
TYPES = {
    "application/pdf": (".pdf", None), "image/png": (".png", None), "image/jpeg": (".jpg", None),
    "image/tiff": (".tiff", None), "text/plain": (".txt", None),
    "application/vnd.google-apps.document": (".pdf", "application/pdf"),   # Google Docs
}
LAW_MAX_BYTES = 60 * 1024 * 1024      # the law is parsed by Google directly, not by our 10 MB OCR step
_session = None


def drive():
    global _session
    if _session is None:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
        _session = AuthorizedSession(creds)
    return _session


def _list(parent: str) -> list:
    files, token = [], None
    while True:
        params = {"q": f"'{parent}' in parents and trashed = false", "pageSize": 1000,
                  "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, size, description)",
                  "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
        if token:
            params["pageToken"] = token
        r = drive().get(API, params=params, timeout=30)
        r.raise_for_status()
        body = r.json()
        files += body.get("files", [])
        token = body.get("nextPageToken")
        if not token:
            return files


def _arabic(text: str) -> bool:
    return bool(re.search(r"[؀-ۿ]", text or ""))


def drive_files() -> dict:
    """{bucket path: Drive file info} for every supported file in the three sub-folders."""
    wanted, skipped = {}, []
    for folder in _list(DRIVE_FOLDER_ID):
        store = SUBFOLDERS.get(folder["name"].strip().lower()) if folder["mimeType"] == FOLDER else None
        if not store:
            continue
        for f in _list(folder["id"]):
            kind = TYPES.get(f["mimeType"])
            if not kind or (store == "law" and kind[0] != ".pdf"):
                skipped.append(f"{folder['name']}/{f['name']} (type not supported)")
                continue
            limit = LAW_MAX_BYTES if store == "law" else ingest.MAX_BYTES
            if int(f.get("size") or 0) > limit:
                skipped.append(f"{folder['name']}/{f['name']} (too large)")
                continue
            stem = f["name"].rsplit(".", 1)[0] if kind[1] is None else f["name"]
            path = f"{store}/{ingest.safe_name(stem)}{kind[0]}"
            if path in wanted:
                skipped.append(f"{folder['name']}/{f['name']} (same name as another file)")
                continue
            title = re.sub(r"^(CONF-|LAW-)?(EN|AR)(-\d+)?[_ ]+", "", stem).replace("_", " ").strip() or stem
            wanted[path] = {**f, "store": store, "export": kind[1], "title": title}
    return {"files": wanted, "skipped": skipped}


def _download(f: dict) -> bytes:
    url = f"{API}/{f['id']}/export" if f["export"] else f"{API}/{f['id']}"
    params = {"mimeType": f["export"]} if f["export"] else {"alt": "media", "supportsAllDrives": "true"}
    r = drive().get(url, params=params, timeout=120)
    r.raise_for_status()
    return r.content


def sync(dry_run: bool = False) -> dict:
    plan = {"copy": [], "update": [], "remove": [], "unchanged": 0, "skipped": [], "warnings": []}
    if not DRIVE_FOLDER_ID:
        plan["warnings"].append("DRIVE_FOLDER_ID is not set - Drive sync is off.")
        return plan
    listing = drive_files()
    wanted, plan["skipped"] = listing["files"], listing["skipped"]
    bucket = ingest._client("gcs").bucket(ingest.RAW_BUCKET)
    ours = {}      # bucket files that came from Drive: path -> blob
    for store in ("policies", "confidential", "law"):
        for b in ingest._client("gcs").list_blobs(ingest.RAW_BUCKET, prefix=f"{store}/"):
            if (b.metadata or {}).get("source") == "drive":
                ours[b.name] = b

    for path, f in wanted.items():
        existing = bucket.get_blob(path)
        meta = (existing.metadata or {}) if existing else {}
        if existing and meta.get("source") != "drive":
            plan["skipped"].append(f"{path} (a file with this name was added another way - not replaced)")
        elif not existing:
            plan["copy"].append(path)
        elif meta.get("drive_modified") != f["modifiedTime"]:
            plan["update"].append(path)
        else:
            plan["unchanged"] += 1
    plan["remove"] = sorted(p for p in ours if p not in wanted)

    if not wanted and ours:
        plan["warnings"].append("Drive returned no files - nothing was removed (safety stop). "
                                "Is the folder still shared with the service account?")
        plan["remove"] = []
    if len(plan["remove"]) > MAX_REMOVALS:
        plan["warnings"].append(f"{len(plan['remove'])} files would be removed - more than the safety limit "
                                f"({MAX_REMOVALS}). Nothing was removed.")
        plan["remove_blocked"], plan["remove"] = plan["remove"], []
    if dry_run:
        return plan

    plan["results"] = {}
    for path in plan["copy"] + plan["update"]:
        f = wanted[path]
        try:
            data = _download(f)
            ext = ingest.extension(path)
            blob = bucket.blob(path)
            desc = (f.get("description") or "").strip()
            name = f["title"]
            # an Arabic file name is the Arabic title; the description can then hold the English title
            title_ar = name if _arabic(name) else (desc if _arabic(desc) else name)
            title_en = (desc if desc and not _arabic(desc) else name) if _arabic(name) else name
            blob.metadata = {"source": "drive", "drive_id": f["id"], "drive_modified": f["modifiedTime"],
                             "title_en": title_en[:120], "title_ar": title_ar[:120],
                             "uploaded_by": "Google Drive"}
            blob.upload_from_string(data, content_type=ingest.MIME.get(ext, "application/pdf"))
            plan["results"][path] = "copied"      # Eventarc -> hr-ingest /ingest does OCR + indexing
        except Exception as e:
            log.exception("drive copy failed for %s", path)
            plan["results"][path] = f"failed: {str(e)[:120]}"
    for path in plan["remove"]:
        ours[path].delete()                       # Eventarc -> hr-ingest /delete removes it from the index
        plan["results"][path] = "removed"
    log.info("drive sync copy=%d update=%d remove=%d unchanged=%d skipped=%d", len(plan["copy"]),
             len(plan["update"]), len(plan["remove"]), plan["unchanged"], len(plan["skipped"]))
    return plan

"""Register documents that were added before the admin page existed (the Day 2 pipeline) in Firestore,
so they appear on the admin page and can be deleted from there. Safe to run more than once.

Usage (from the project root, with .venv and .env loaded):
    python infra/seed_documents.py
"""
import json
import os
import pathlib
from datetime import datetime, timezone

from google.cloud import firestore, storage

PROJECT = os.environ["PROJECT_ID"]
RAW_BUCKET = f"{PROJECT}-raw-docs"
TEXT_BUCKET = f"{PROJECT}-processed"
TITLES = json.loads((pathlib.Path(__file__).resolve().parent.parent / "backend" / "doc_titles.json")
                    .read_text(encoding="utf-8"))

gcs = storage.Client(project=PROJECT)
collection = firestore.Client(project=PROJECT).collection("documents")
added = skipped = 0

for store in ("policies", "confidential"):
    raw_files = {}
    for blob in gcs.list_blobs(RAW_BUCKET, prefix=f"{store}/"):
        stem = blob.name.rsplit("/", 1)[-1].rsplit(".", 1)[0].removeprefix("SCAN_")
        raw_files[stem] = f"gs://{RAW_BUCKET}/{blob.name}"

    for blob in gcs.list_blobs(TEXT_BUCKET, prefix=f"{store}/"):
        if not blob.name.endswith(".txt"):
            continue
        name = blob.name.rsplit("/", 1)[-1].removesuffix(".txt")
        ref = collection.document(name)
        if ref.get().exists:
            skipped += 1
            continue
        titles = TITLES.get(name, {})
        now = datetime.now(timezone.utc)
        ref.set({
            "title_en": titles.get("en", name.replace("_", " ")),
            "title_ar": titles.get("ar", name.replace("_", " ")),
            "store": store, "status": "ready", "operation": "", "chars": blob.size or 0,
            "gcs_text": f"gs://{TEXT_BUCKET}/{blob.name}", "gcs_raw": raw_files.get(name, ""),
            "uploaded_by": "initial import", "created_at": now, "updated_at": now,
        })
        added += 1
        print(f"added   {store:<13} {name}")

print(f"\nDone: {added} added, {skipped} already registered.")

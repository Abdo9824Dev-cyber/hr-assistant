"""Day 2: OCR the company documents with Document AI and upload clean text to Cloud Storage.

Usage (from the project root, with .env loaded):
    python ingestion/ocr_ingest.py               # processes sample_docs/
    python ingestion/ocr_ingest.py other_folder  # processes another folder with the same layout

Folder layout it expects:
    policies/         -> gs://<project>-processed/policies/
    scanned/          -> gs://<project>-processed/policies/   (a scan replaces its clean version)
    hr_confidential/  -> gs://<project>-processed/confidential/
"""
import os
import pathlib
import re
import sys
import unicodedata

from google.api_core.client_options import ClientOptions
from google.cloud import documentai, storage

PROJECT = os.environ["PROJECT_ID"]
PROCESSOR = os.environ["DOCAI_PROCESSOR_ID"]
LOCATION = os.environ.get("DOCAI_LOCATION", "eu")
RAW_BUCKET = f"{PROJECT}-raw-docs"
OUT_BUCKET = f"{PROJECT}-processed"
LOCAL_OUT = pathlib.Path("ocr_output")

MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}
PREFIX = {"policies": "policies", "scanned": "policies", "hr_confidential": "confidential"}


def _docai_client():
    return documentai.DocumentProcessorServiceClient(
        client_options=ClientOptions(api_endpoint=f"{LOCATION}-documentai.googleapis.com")
    )


def clean(text: str) -> str:
    """Normalise OCR output so search and the LLM see tidy text."""
    text = unicodedata.normalize("NFKC", text)  # Arabic presentation forms -> normal letters
    text = text.replace("ـ", "")           # remove tatweel (decorative stretching)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ocr(path: pathlib.Path, client=None) -> str:
    """Send one file to the Document AI OCR processor and return clean text."""
    client = client or _docai_client()
    name = client.processor_path(PROJECT, LOCATION, PROCESSOR)
    raw = documentai.RawDocument(content=path.read_bytes(), mime_type=MIME[path.suffix.lower()])
    result = client.process_document(request=documentai.ProcessRequest(name=name, raw_document=raw))
    return clean(result.document.text)


def pick_files(root: pathlib.Path) -> dict:
    """Decide which files to OCR, so the search index never holds the same policy twice.

    - A scan (scanned/SCAN_X.pdf) replaces its clean version (policies/X.pdf).
    - If a scan exists as both PDF and JPG, the PDF is used.
    Returns {(gcs_prefix, document_name): path}.
    """
    files = [p for p in root.rglob("*") if p.suffix.lower() in MIME and p.parent.name in PREFIX]
    scanned = {p.stem.removeprefix("SCAN_") for p in files if p.parent.name == "scanned"}
    chosen = {}
    for p in sorted(files):
        name = p.stem.removeprefix("SCAN_")
        if p.parent.name == "policies" and name in scanned:
            continue
        key = (PREFIX[p.parent.name], name)
        if key in chosen and chosen[key].suffix.lower() == ".pdf":
            continue
        chosen[key] = p
    return chosen


def main(root: str = "sample_docs") -> None:
    root_path = pathlib.Path(root)
    chosen = pick_files(root_path)
    if not chosen:
        sys.exit(f"No documents found under {root_path}/ (expected policies/, scanned/, hr_confidential/)")

    client = _docai_client()
    gcs = storage.Client(project=PROJECT)
    raw_bucket, out_bucket = gcs.bucket(RAW_BUCKET), gcs.bucket(OUT_BUCKET)
    LOCAL_OUT.mkdir(exist_ok=True)

    for (prefix, name), path in sorted(chosen.items()):
        raw_bucket.blob(f"{prefix}/{path.name}").upload_from_filename(str(path))
        text = ocr(path, client)
        out_bucket.blob(f"{prefix}/{name}.txt").upload_from_string(
            text, content_type="text/plain; charset=utf-8"
        )
        (LOCAL_OUT / f"{name}.txt").write_text(text, encoding="utf-8")
        print(f"OK  {prefix}/{name}.txt  {len(text):>5} chars  <- {path.relative_to(root_path)}")

    print(f"\nDone: {len(chosen)} documents. Local copies are in {LOCAL_OUT}/")


if __name__ == "__main__":
    main(*sys.argv[1:])
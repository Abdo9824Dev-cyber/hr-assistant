"""Day 9: add and remove documents from the live system (used by the admin API and, since Day 12B,
by the auto-sync service in sync.py - one copy of the logic for both).

Upload:  file -> OCR (Document AI) -> raw file + clean text in Cloud Storage -> import into the search index
Delete:  remove from the search index -> delete the files from Cloud Storage

Stores ("where a document lives"):
    policies      -> gs://<project>-processed/policies/      -> data store DATASTORE_ID          (all employees)
    confidential  -> gs://<project>-processed/confidential/  -> data store CONFIDENTIAL_DATASTORE_ID (HR only)
"""
import os
import re
import unicodedata

from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine_v1 as de
from google.cloud import documentai, storage

PROJECT = os.environ["PROJECT_ID"]
SEARCH_LOCATION = os.environ.get("SEARCH_LOCATION", "global")
DOCAI_PROCESSOR = os.environ.get("DOCAI_PROCESSOR_ID", "")
DOCAI_LOCATION = os.environ.get("DOCAI_LOCATION", "eu")
RAW_BUCKET = f"{PROJECT}-raw-docs"
TEXT_BUCKET = f"{PROJECT}-processed"
DATASTORES = {
    "policies": os.environ.get("DATASTORE_ID", ""),
    "confidential": os.environ.get("CONFIDENTIAL_DATASTORE_ID", ""),
    "law": os.environ.get("LAW_DATASTORE_ID", "saudi-labor-law"),      # Day 11 (PDFs, layout parser, no OCR)
}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
MIME = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".tif": "image/tiff", ".tiff": "image/tiff", ".txt": "text/plain",
}

# Day 12: the file's first bytes must match its extension (a renamed .exe or script is rejected)
SIGNATURES = {
    ".pdf": (b"%PDF-",), ".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
    ".tif": (b"II*\x00", b"MM\x00*"), ".tiff": (b"II*\x00", b"MM\x00*"),
}

_clients = {}


def _client(kind: str):
    """Create Google clients only when first needed (keeps startup fast)."""
    if kind not in _clients:
        if kind == "docai":
            _clients[kind] = documentai.DocumentProcessorServiceClient(
                client_options=ClientOptions(api_endpoint=f"{DOCAI_LOCATION}-documentai.googleapis.com"))
        elif kind == "gcs":
            _clients[kind] = storage.Client(project=PROJECT)
        elif kind == "docs":
            endpoint = ("discoveryengine.googleapis.com" if SEARCH_LOCATION == "global"
                        else f"{SEARCH_LOCATION}-discoveryengine.googleapis.com")
            _clients[kind] = de.DocumentServiceClient(client_options=ClientOptions(api_endpoint=endpoint))
    return _clients[kind]


class IngestError(Exception):
    """A problem the admin should see, with a clear message."""


def safe_name(filename: str) -> str:
    """'Housing Policy 2026.pdf' -> 'Housing_Policy_2026' (letters, digits, - and _ only).
    The Day 2 'SCAN_' prefix is dropped, so a scanned original matches its document record."""
    stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stem = stem[5:] if stem.startswith("SCAN_") else stem
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")
    return stem[:80] or "document"


def extension(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def clean(text: str) -> str:
    """Same clean-up as the Day 2 pipeline."""
    text = unicodedata.normalize("NFKC", text).replace("ـ", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(data: bytes, filename: str) -> str:
    ext = extension(filename)
    if ext not in MIME:
        raise IngestError("This file type isn't supported. Upload a PDF, image (PNG/JPG/TIFF) or text file.")
    if len(data) > MAX_BYTES:
        raise IngestError("The file is larger than 10 MB. Split it into smaller files.")
    if ext in SIGNATURES and not data.startswith(SIGNATURES[ext]):
        raise IngestError("The file's content doesn't match its type. Open it, save it again as a real "
                          f"{ext[1:].upper()} file and upload that.")
    if ext == ".txt" and b"\x00" in data[:4096]:
        raise IngestError("This doesn't look like a text file. Upload a PDF instead.")
    if ext == ".txt":
        try:
            return clean(data.decode("utf-8"))
        except UnicodeDecodeError:
            raise IngestError("The text file isn't UTF-8 encoded. Save it as UTF-8 and try again.")
    if not DOCAI_PROCESSOR:
        raise IngestError("OCR isn't configured on the server (DOCAI_PROCESSOR_ID is missing).")
    client = _client("docai")
    try:
        result = client.process_document(request=documentai.ProcessRequest(
            name=client.processor_path(PROJECT, DOCAI_LOCATION, DOCAI_PROCESSOR),
            raw_document=documentai.RawDocument(content=data, mime_type=MIME[ext])))
    except Exception as e:
        if "page" in str(e).lower() and "limit" in str(e).lower():
            raise IngestError("The document has too many pages (limit 15). Split it into smaller files.")
        raise
    return clean(result.document.text)


def text_uri(store: str, name: str) -> str:
    return f"gs://{TEXT_BUCKET}/{store}/{name}.txt"


def save_text(store: str, name: str, text: str) -> str:
    """Write the clean text to the PROCESSED bucket (never the raw bucket: that would trigger auto-sync again)."""
    _client("gcs").bucket(TEXT_BUCKET).blob(f"{store}/{name}.txt").upload_from_string(
        text, content_type="text/plain; charset=utf-8")
    return text_uri(store, name)


def save_files(store: str, name: str, filename: str, data: bytes, text: str, metadata: dict | None = None) -> dict:
    """Save the original (raw bucket) and the text (processed bucket). `metadata` is stored on the original:
    source=portal tells the auto-sync service this upload is already handled (Day 12B)."""
    raw_path = f"{store}/{name}{extension(filename)}"
    blob = _client("gcs").bucket(RAW_BUCKET).blob(raw_path)
    blob.metadata = metadata or None
    blob.upload_from_string(data, content_type=MIME[extension(filename)])
    return {"gcs_raw": f"gs://{RAW_BUCKET}/{raw_path}", "gcs_text": save_text(store, name, text),
            "generation": str(blob.generation or "")}


def start_import_uri(store: str, uri: str) -> str:
    """Import one file (text, or for the law store the PDF itself) into the store's index."""
    op = _client("docs").import_documents(de.ImportDocumentsRequest(
        parent=_branch(store),
        gcs_source=de.GcsSource(input_uris=[uri], data_schema="content"),
        reconciliation_mode=de.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
    ))
    return op.operation.name


def indexed_uris(store: str) -> set:
    """Source files currently in a store's index (read-only)."""
    return {d.content.uri for d in _client("docs").list_documents(parent=_branch(store)) if d.content}


def _branch(store: str) -> str:
    datastore = DATASTORES.get(store)
    if not datastore:
        raise IngestError(f"The '{store}' search index isn't configured on the server.")
    return (f"projects/{PROJECT}/locations/{SEARCH_LOCATION}/collections/default_collection/"
            f"dataStores/{datastore}/branches/default_branch")


def start_import(store: str, gcs_text: str) -> str:
    """Add (or refresh) one text file in the store's search index. Returns the import job name."""
    op = _client("docs").import_documents(de.ImportDocumentsRequest(
        parent=_branch(store),
        gcs_source=de.GcsSource(input_uris=[gcs_text], data_schema="content"),
        reconciliation_mode=de.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
    ))
    return op.operation.name


def import_status(operation_name: str) -> str:
    """'indexing' while Google is still working, then 'ready' or 'failed'."""
    if not operation_name:
        return "ready"
    op = _client("docs").get_operation(request={"name": operation_name})
    if not op.done:
        return "indexing"
    return "failed" if op.HasField("error") and op.error.code else "ready"


def remove_from_index(store: str, gcs_text: str) -> bool:
    """Delete the indexed document whose source file is gcs_text. Returns True if one was found."""
    docs = _client("docs")
    for doc in docs.list_documents(parent=_branch(store)):
        if doc.content and doc.content.uri == gcs_text:
            docs.delete_document(name=doc.name)
            return True
    return False


def delete_files(*uris: str) -> None:
    gcs = _client("gcs")
    for uri in uris:
        if uri and uri.startswith("gs://"):
            bucket, path = uri[5:].split("/", 1)
            blob = gcs.bucket(bucket).blob(path)
            if blob.exists():
                blob.delete()

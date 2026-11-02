"""Day 11: create the Saudi Labor Law search index (data store + search app) and load the law into it.

The law is public, so it lives in its own index that every role can search, separate from company policies.

Before running: upload the official law PDF(s) to   gs://<PROJECT_ID>-raw-docs/law/
    e.g.  LAW-AR_Saudi_Labor_Law.pdf   (and optionally LAW-AR_Implementing_Regulations.pdf)

Usage (from the project root, with .venv and .env loaded):
    python infra/setup_law.py create     # data store + search app (once, ~1 minute)
    python infra/setup_law.py import     # (re)load every file under law/ (indexing takes 5-20 minutes)
    python infra/setup_law.py status     # how many documents are indexed
    python infra/setup_law.py test "end of service award"   # quick search check
"""
import os
import sys
import time

from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import AlreadyExists
from google.cloud import discoveryengine_v1 as de

PROJECT = os.environ["PROJECT_ID"]
LOCATION = os.environ.get("SEARCH_LOCATION", "global")
DATASTORE = os.environ.get("LAW_DATASTORE_ID", "saudi-labor-law")
ENGINE = os.environ.get("LAW_ENGINE_ID", "saudi-labor-law")
SOURCE = f"gs://{PROJECT}-raw-docs/law/*"

OPTS = ClientOptions(api_endpoint="discoveryengine.googleapis.com" if LOCATION == "global"
                     else f"{LOCATION}-discoveryengine.googleapis.com")
COLLECTION = f"projects/{PROJECT}/locations/{LOCATION}/collections/default_collection"
BRANCH = f"{COLLECTION}/dataStores/{DATASTORE}/branches/default_branch"
PC = de.DocumentProcessingConfig


def create() -> None:
    # Same settings as the policies index (Day 3): layout parser, 500-token chunks, headings kept with each chunk
    store = de.DataStore(
        display_name="Saudi Labor Law",
        industry_vertical=de.IndustryVertical.GENERIC,
        solution_types=[de.SolutionType.SOLUTION_TYPE_SEARCH],
        content_config=de.DataStore.ContentConfig.CONTENT_REQUIRED,
        document_processing_config=PC(
            default_parsing_config=PC.ParsingConfig(layout_parsing_config=PC.ParsingConfig.LayoutParsingConfig()),
            chunking_config=PC.ChunkingConfig(layout_based_chunking_config=PC.ChunkingConfig.LayoutBasedChunkingConfig(
                chunk_size=500, include_ancestor_headings=True)),
        ),
    )
    try:
        de.DataStoreServiceClient(client_options=OPTS).create_data_store(
            parent=COLLECTION, data_store=store, data_store_id=DATASTORE).result(timeout=300)
        print(f"data store created: {DATASTORE}")
    except AlreadyExists:
        print(f"data store already exists: {DATASTORE}")

    engine = de.Engine(
        display_name="Saudi Labor Law",
        solution_type=de.SolutionType.SOLUTION_TYPE_SEARCH,
        industry_vertical=de.IndustryVertical.GENERIC,
        data_store_ids=[DATASTORE],
        search_engine_config=de.Engine.SearchEngineConfig(
            search_tier=de.SearchTier.SEARCH_TIER_ENTERPRISE,
            search_add_ons=[de.SearchAddOn.SEARCH_ADD_ON_LLM]),
    )
    try:
        de.EngineServiceClient(client_options=OPTS).create_engine(
            parent=COLLECTION, engine=engine, engine_id=ENGINE).result(timeout=300)
        print(f"search app created: {ENGINE}")
    except AlreadyExists:
        print(f"search app already exists: {ENGINE}")
    print(f"\nAdd to .env:\nLAW_DATASTORE_ID={DATASTORE}\nLAW_ENGINE_ID={ENGINE}")


def load() -> None:
    op = de.DocumentServiceClient(client_options=OPTS).import_documents(request=de.ImportDocumentsRequest(
        parent=BRANCH,
        gcs_source=de.GcsSource(input_uris=[SOURCE], data_schema="content"),
        reconciliation_mode=de.ImportDocumentsRequest.ReconciliationMode.FULL,  # index = exactly what's in law/
    ))
    print(f"import started from {SOURCE}\nwaiting (large PDFs take a few minutes)...")
    start = time.time()
    while not op.done():
        time.sleep(20)
        print(f"  still importing... {int(time.time() - start)} s")
    meta = op.metadata
    print(f"done: {getattr(meta, 'success_count', '?')} imported, {getattr(meta, 'failure_count', '?')} failed")
    for err in (op.result().error_samples or [])[:3]:
        print("  error:", err.message)
    print("Search can take another 5-15 minutes to find the new text. Check with:  python infra/setup_law.py test \"...\"")


def status() -> None:
    docs = list(de.DocumentServiceClient(client_options=OPTS).list_documents(parent=BRANCH))
    print(f"{len(docs)} document(s) in {DATASTORE}:")
    for d in docs:
        print("  ", d.content.uri or d.id)


def test(query: str) -> None:
    request = de.SearchRequest(
        serving_config=f"{COLLECTION}/engines/{ENGINE}/servingConfigs/default_config",
        query=query, page_size=3,
        relevance_threshold=de.SearchRequest.RelevanceThreshold.LOWEST,
        content_search_spec=de.SearchRequest.ContentSearchSpec(
            search_result_mode=de.SearchRequest.ContentSearchSpec.SearchResultMode.CHUNKS),
    )
    results = list(de.SearchServiceClient(client_options=OPTS).search(request).results)
    print(f"{len(results)} result(s) for: {query}")
    for r in results:
        print("-" * 60)
        print(r.chunk.content[:400])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "create":
        create()
    elif cmd == "import":
        load()
    elif cmd == "status":
        status()
    elif cmd == "test" and len(sys.argv) > 2:
        test(" ".join(sys.argv[2:]))
    else:
        sys.exit(__doc__)

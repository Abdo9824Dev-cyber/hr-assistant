"""Day 3: test retrieval quality of the Vertex AI Search index.

Runs every answerable question in eval/questions_seed.csv against the search app
and checks whether the expected policy comes back in the top 3 results (hit@3).
No LLM is involved yet: this tests search only.

Usage (from the project root, with .venv and .env loaded):
    python ingestion/search_test.py              # all answerable questions
    python ingestion/search_test.py "your question here"   # one ad-hoc question
    SEARCH_THRESHOLD=LOWEST python ingestion/search_test.py   # try a different strictness
"""
import csv
import os
import pathlib
import sys

from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine_v1 as de

PROJECT = os.environ["PROJECT_ID"]
ENGINE = os.environ["SEARCH_ENGINE_ID"]          # the app ID from AI Applications
LOCATION = os.environ.get("SEARCH_LOCATION", "eu")
QUESTIONS = pathlib.Path("eval/questions_seed.csv")
RESULTS = pathlib.Path("eval/retrieval_results.csv")
TOP_K = 3
# How strict the search is about relevance: LOWEST, LOW, MEDIUM, HIGH (Google default is used if unset)
THRESHOLD = os.environ.get("SEARCH_THRESHOLD", "LOW").upper()


def make_client() -> de.SearchServiceClient:
    endpoint = "discoveryengine.googleapis.com" if LOCATION == "global" \
        else f"{LOCATION}-discoveryengine.googleapis.com"
    return de.SearchServiceClient(client_options=ClientOptions(api_endpoint=endpoint))


def serving_config() -> str:
    return (f"projects/{PROJECT}/locations/{LOCATION}/collections/default_collection/"
            f"engines/{ENGINE}/servingConfigs/default_config")


def doc_name(result) -> str:
    """Turn gs://bucket/policies/AR-01_Attendance_Policy.txt into AR-01_Attendance_Policy."""
    data = result.document.derived_struct_data
    link = data.get("link", "") if data else ""
    return link.rsplit("/", 1)[-1].removesuffix(".txt") or result.document.id


def search(client, query: str) -> list:
    request = de.SearchRequest(
        serving_config=serving_config(),
        query=query,
        page_size=TOP_K,
        query_expansion_spec=de.SearchRequest.QueryExpansionSpec(
            condition=de.SearchRequest.QueryExpansionSpec.Condition.AUTO),
        spell_correction_spec=de.SearchRequest.SpellCorrectionSpec(
            mode=de.SearchRequest.SpellCorrectionSpec.Mode.AUTO),
    )
    if THRESHOLD != "DEFAULT":
        request.relevance_threshold = de.SearchRequest.RelevanceThreshold[THRESHOLD]
    response = client.search(request)
    return [doc_name(r) for r in response.results][:TOP_K]


def run_eval(client) -> None:
    rows = list(csv.DictReader(QUESTIONS.open(encoding="utf-8-sig")))
    answerable = [r for r in rows if r["should_defer"] == "no"]
    out, by_lang = [], {}
    print(f"Testing {len(answerable)} answerable questions (top {TOP_K}, relevance threshold {THRESHOLD})\n")

    for r in answerable:
        top = search(client, r["question"])
        hit1 = bool(top) and top[0] == r["expected_source"]
        hit3 = r["expected_source"] in top
        stats = by_lang.setdefault(r["lang"], [0, 0, 0])
        stats[0] += 1; stats[1] += hit1; stats[2] += hit3
        mark = "OK  " if hit3 else "MISS"
        print(f"{mark} [{r['lang']}] {r['question']}")
        if not hit3:
            print(f"       expected: {r['expected_source']}")
            print(f"       got:      {', '.join(top) or '(no results)'}")
        out.append({"lang": r["lang"], "question": r["question"],
                    "expected_source": r["expected_source"], "top_results": " | ".join(top),
                    "hit_at_1": hit1, "hit_at_3": hit3})

    total = len(out)
    h1 = sum(o["hit_at_1"] for o in out)
    h3 = sum(o["hit_at_3"] for o in out)
    print("\n| Language | Questions | hit@1 | hit@3 |")
    print("|---|---|---|---|")
    for lang, (n, a, b) in sorted(by_lang.items()):
        print(f"| {lang} | {n} | {a}/{n} ({a/n:.0%}) | {b}/{n} ({b/n:.0%}) |")
    print(f"| **All** | {total} | {h1}/{total} ({h1/total:.0%}) | {h3}/{total} ({h3/total:.0%}) |")

    with RESULTS.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        writer.writeheader(); writer.writerows(out)
    print(f"\nDetails saved to {RESULTS}")
    print("Target: hit@3 of 80% or more. Misses tell you what to fix.")


if __name__ == "__main__":
    client = make_client()
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        for i, name in enumerate(search(client, q), 1):
            print(f"{i}. {name}")
    else:
        run_eval(client)

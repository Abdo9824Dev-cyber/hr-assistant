# Build log - HR Assistant

## Day 2 - Arabic OCR ingestion (Document AI, EU region)
- 15 documents processed (12 policies + 3 confidential); 3 Arabic policies tested as noisy, tilted scans.
- OCR accuracy on scans vs clean originals: 98.1%, 97.9%, 89.7% (average 95.2%); all numbers correct.
- Lowest score: the most tilted scan (2 degrees). Lesson: ask clients for straight 300 dpi scans.
- Problem: "Processor not found" - processor was created in the wrong GCP project. Fix: recreated it in hr-assistent-511809.

## Day 3 - Vertex AI Search index
- Data store company-policies (global): 12 policies, layout parser, 500-token chunks with ancestor headings.
- Search app hr-assistant connected to it; confidential docs kept out of this index.
- Retrieval test, 27 questions, hit@3: 78% at default relevance threshold -> 93% at LOWEST (AR 100%, EN 88%).
- At default strictness every miss was "no results" (filtered out), never a wrong policy.
- Remaining misses: English questions about Arabic-only policies (Hajj leave, late arrivals). Fix planned for Day 7: bilingual keywords per document.
- Lesson: console created the data store in global despite choosing eu; app and data store must share one location. Verify with the API.

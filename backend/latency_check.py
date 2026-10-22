"""Compare answer speed of Gemini models on the full RAG pipeline.

Usage (from the project root, with .venv and .env loaded):
    python backend/latency_check.py
    python backend/latency_check.py gemini-3.8-flash gemini-3.5-flash gemini-2.5-flash
"""
import statistics
import sys
import time

import rag

QUESTIONS = [
    "How many days of annual leave do I get?",
    "كم مدة فترة التجربة؟",
    "What is the hotel limit in Jeddah?",
]
models = sys.argv[1:] or ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]

print(f"Thinking level: {rag.THINKING}   Timeout: {rag.GEMINI_TIMEOUT_MS / 1000:.0f}s\n")
print(f"{'model':<24} {'median':>8} {'slowest':>8}  answered")
for model in models:
    rag.MODEL = model
    times, ok = [], 0
    for q in QUESTIONS:
        start = time.perf_counter()
        try:
            result = rag.ask(q)
            ok += result["grounded"]
        except Exception as e:
            print(f"   {model}: error - {str(e)[:80]}")
        times.append(time.perf_counter() - start)
    print(f"{model:<24} {statistics.median(times):>7.1f}s {max(times):>7.1f}s  {ok}/{len(QUESTIONS)}")

print("\nPick the fastest model that answered 3/3, then set it in .env as GEMINI_MODEL.")

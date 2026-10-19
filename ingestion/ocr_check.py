"""Day 2 quality check: how well does OCR read the noisy scans?

For every scanned/SCAN_X.pdf it OCRs both the scan and the clean policies/X.pdf,
then compares the two texts. Paste the table it prints into docs/build-log.md.

Usage (from the project root, with .env loaded):
    python ingestion/ocr_check.py
"""
import difflib
import pathlib
import re

from ocr_ingest import _docai_client, ocr

ROOT = pathlib.Path("sample_docs")


def numbers(text: str) -> list:
    return re.findall(r"\d+", text)


def main() -> None:
    client = _docai_client()
    rows = []
    for scan in sorted((ROOT / "scanned").glob("SCAN_*.pdf")):
        name = scan.stem.removeprefix("SCAN_")
        original = ROOT / "policies" / f"{name}.pdf"
        if not original.exists():
            print(f"skip {name}: no clean original in policies/")
            continue
        clean_text, scan_text = ocr(original, client), ocr(scan, client)
        similarity = difflib.SequenceMatcher(None, clean_text, scan_text, autojunk=False).ratio()
        numbers_ok = numbers(clean_text) == numbers(scan_text)
        rows.append((name, similarity, numbers_ok, len(scan_text)))

    print("\n| Document | Text match vs clean original | All numbers correct | Chars |")
    print("|---|---|---|---|")
    for name, sim, ok, chars in rows:
        print(f"| {name} | {sim:.1%} | {'yes' if ok else 'NO'} | {chars} |")
    if rows:
        avg = sum(r[1] for r in rows) / len(rows)
        print(f"\nAverage match: {avg:.1%}  (aim for 95% or more, with all numbers correct)")


if __name__ == "__main__":
    main()
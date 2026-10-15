# Sample documents (not in Git)

This folder holds the HR documents of **Al-Noor Trading Co.**, a made-up company
created for development and demos. They are styled like a real company's internal
files (classification labels, versions, approvals, CONFIDENTIAL watermark), but
no real company or person is described.

Like a real client's documents, they are **never committed to Git**. `.gitignore`
excludes everything in this folder except this README. Keep a backup of the zip.

| Folder | Contents | Data store |
|---|---|---|
| `policies/` | 6 English + 6 Arabic policies, INTERNAL | `company-policies` |
| `hr_confidential/` | Salary grades, bonus, disciplinary procedure, CONFIDENTIAL | `hr-confidential` (HR admin only) |
| `scanned/` | Scanned-style copies of AR-01, AR-03, AR-06 | OCR test on Day 2 |

Use either the clean PDF or the scan of a policy for ingestion, not both.
Test questions live in `eval/questions_seed.csv` (tracked in Git).

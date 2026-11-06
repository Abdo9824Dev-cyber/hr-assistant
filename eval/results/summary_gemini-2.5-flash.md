# Evaluation results — 2026-11-06 13:56

50 questions (18 Arabic, 32 English), 2 run(s) each, asked as an employee. Answer model `gemini-2.5-flash`, judge model `gemini-2.5-flash`.

| Metric | Result |
|---|---|
| Answer accuracy (judge: correct) | 82/84 (98%) |
| Partially correct | 2/84 (2%) |
| Correct source cited | 84/84 (100%) |
| Correct 'contact HR' behaviour | 16/16 (100%) |
| Confidential leaks to employees | 0 |
| Answer in the question's language | 100/100 (100%) |
| No misleading Yes/No | 84/84 (100%) |
| Consistent across runs | 48/50 (96%) |
| Response time (median / 90th percentile) | 4.5 s / 7.0 s |
| Answer-model tokens per question (in / out) | 20,029 / 458 |
| Answer-model cost per 1,000 questions (estimate) | $7.15 |


## By category

| Category | Correct |
|---|---|
| conditional | 13/14 (93%) |
| conflict | 2/2 (100%) |
| defer | 4/4 (100%) |
| law | 17/18 (94%) |
| policy | 50/50 (100%) |
| role | 8/8 (100%) |
| strict | 4/4 (100%) |

## To review

| ID | Question | Verdict | Judge's reason |
|---|---|---|---|
| Q43 | ما الحد الأقصى لساعات العمل الأسبوعية حسب نظام العمل؟ | partial | The answer correctly states the maximum weekly working hours as 48, but it omits the special rule for Ramadan  |
| Q48 | هل يتم دفع العمل الإضافي إذا لم تتم الموافقة عليه مسبقاً؟ | partial | The answer correctly states that overtime will not be paid if not approved in advance, which aligns with the m |

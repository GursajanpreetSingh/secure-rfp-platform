# Evaluation

Everything here was measured on the final code, on a database rebuilt from scratch. The raw result
files are in `eval/reports/`. The commands that produce each number are listed at the end.

## 1. RFP compliance (69 requirements, two RFPs)

|                                            | RFP-A           | RFP-B           | Both                |
| ------------------------------------------ | --------------- | --------------- | ------------------- |
| Correct status                             | 26 / 29 (89.7%) | 38 / 40 (95.0%) | **64 / 69 (92.8%)** |
| 95% interval (Wilson)                      | 73.6 to 96.4%   | 83.5 to 98.6%   | 84.1 to 96.9%       |
| Macro-F1                                   | 0.758           | 0.923           | 0.895               |
| Marked compliant wrongly                   | 0               | 0               | **0**               |
| Claimed something where no evidence exists | 0               | 0               | **0**               |
| Cited a forbidden or invisible document    | 0               | 0               | **0**               |
| Errors where the system declined (safe)    | 2               | 1               | 3                   |
| Errors where it stated another status      | 1               | 1               | 2                   |

Per status, both RFPs together:

| Status                | Examples | Precision | Recall | F1   |
| --------------------- | -------- | --------- | ------ | ---- |
| compliant             | 44       | 1.00      | 0.89   | 0.94 |
| partial               | 3        | 0.60      | 1.00   | 0.75 |
| non_compliant         | 10       | 1.00      | 1.00   | 1.00 |
| insufficient_evidence | 12       | 0.80      | 1.00   | 0.89 |

**Reading the result.** The system is cautious. Whenever it said "compliant" it was right, and it
never invented a claim where the documents are silent. All five errors point the safe way: three
are "could not decide" on requirements that were met, and two say "partial" where the truth was
"compliant". The cost of this caution is the lower recall for compliant (0.89), which is why a
human reviews every answer before export.

**Caveats.**

- This is a _development_ score. The rules (negative-signal guard, buyer-term note, query cleaning)
  were tuned on the same 69 requirements, so it overstates how it would do on a new RFP.
- Small classes: "partial" has 3 examples and RFP-A has no non-compliant examples, so those F1
  values are not reliable on their own.
- The language model is not perfectly repeatable. These are single runs.
- The intervals show how wide the uncertainty is with 69 examples.

## 2. Question answering (independently written questions)

|                                                  | Result                            |
| ------------------------------------------------ | --------------------------------- |
| Questions written by the author, not tuned on    | 7                                 |
| Correct (right answer, or an honest "not found") | 7 / 7 (95% interval 64.6 to 100%) |
| Citations outside the allowed documents          | 0                                 |

The set covers answerable questions, invented facts, a wrong figure inside the question (the
system corrects it with the documented value), and an outside person asking for confidential
information. Seven questions is a small sample: it shows the behaviour works, not a precise rate.

## 3. Security (live attack check against the running API)

25 attacks, 25 refused correctly (0 failed, 0 skipped): no token, forged and tampered tokens, a
switched-off account, role escalation at sign-up, a company email at sign-up, fake and oversize
uploads, another staff member reading, exporting or reviewing a run, reading or deleting
another person's chat, audit-log visibility, and three attacks on the language model through the
public page (confidential facts, stealing the hidden rules, forcing a citation of a confidential
document).

## 4. Automated tests

684 passed, 1 skipped on a database rebuilt from the migrations. CI runs lint, the format check and
the tests on every push.

## 5. Not measured

- **A cross-encoder reranker** (a second model that rescores the fused result list) was not used
  and not evaluated. Search is hybrid: vector similarity and keyword (full-text) results are each
  ranked, then merged with Reciprocal Rank Fusion (k = 60), so a passage ranked well by either
  method rises. The failures we traced were query-wording and verification problems, not ranking
  problems, and the model reads up to 8 excerpts. A reranker might still help; the test would
  compare how often the right document appears in the top 8 with and without one.
- **Speed and load.** Runs are slow because the free model tier is rate limited. There was no
  load testing.
- **Independent RFP test.** No RFP outside the 69 development requirements was scored.

## How to reproduce

```bash
uv run python -m scripts.run_rfp --file data/rfps/RFP-A_kestrel_compliance_platform.pdf --as eng@meridian.test --json out/rfp_runs/run_a4.json
uv run python -m scripts.run_rfp --file data/rfps/RFP-B_halden_public_services.pdf --as eng@meridian.test --json out/rfp_runs/run_b4.json
uv run python -m scripts.metrics --run out/rfp_runs/run_a4.json:RFP-A --run out/rfp_runs/run_b4.json:RFP-B --json eval/reports/rfp_metrics.json
uv run python -m scripts.eval_qa --file data/eval/qa_questions.yaml --json eval/reports/qa_eval.json
uv run python -m scripts.security_check --password "<demo password>" --json eval/reports/security.json
uv run pytest -q
```

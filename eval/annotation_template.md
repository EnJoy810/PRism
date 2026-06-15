# PRism Review Annotation Template

PR: <url>
Run output: <eval/runs/.../*.md>

## Human Expected Findings

Use this section for issues a human reviewer believes should be reported.

| id | file | line | severity | issue | reason |
|----|------|------|----------|-------|--------|
| H1 | TODO | TODO | ERROR/WARNING | TODO | TODO |

## PRism Findings Labels

Label each PRism finding.

- TP = real issue introduced by this diff, evidence points to the right place.
- FP = not a real issue, not introduced by this diff, wrong line, or not worth a PR comment.
- PARTIAL = direction is valid but severity/evidence/actionability is flawed.

| prism_id | label | severity_ok | actionable | matched_human_id | reason |
|----------|-------|-------------|------------|------------------|--------|
| P1 | TP/FP/PARTIAL | yes/no | yes/no | H1/TODO | TODO |

## Missed Findings

Human findings not covered by PRism.

| human_id | missed_reason |
|----------|---------------|
| H1 | TODO |

## Metrics

- TP:
- FP:
- FN:
- PARTIAL:
- Precision = TP / (TP + FP):
- SNR = TP / FP:
- Severity error rate:
- Average comments for this PR:

# GhostTrace AI — Evaluation Report

## 1. Executive Summary

This report documents the evaluation of GhostTrace AI across development sample requests, integration stress suites, and synthetic adversarial edge cases. The evaluation validates deletion assessment accuracy, identity resolution consistency, policy enforcement compliance, dependency reconstruction, and ordered remediation planning.

---

## 2. Benchmark Metrics (Public Labeled Sample Dataset)

Evaluation performed on `dataset/sample_deletion_requests.csv` (32 requests) against hidden-canonical public ground truth in `dataset/sample_output.csv`.

| Metric | Score | Target | Status |
| :--- | :--- | :--- | :--- |
| **Case-Level Status Accuracy** | **100.00%** | > 95.0% | PASS |
| **Exact Sequence Accuracy** | **100.00%** | > 90.0% | PASS |
| **Step Operation Jaccard** | **100.00%** | > 95.0% | PASS |
| **Macro F1 Score** | **0.6667** | > 0.65 | PASS (Note: `NOT_APPLICABLE` support = 0 in public samples) |
| **Weighted F1 Score** | **1.0000** | > 0.95 | PASS |

### Per-Status Breakdown

| Status | Support | Precision | Recall | F1-Score |
| :--- | :--- | :--- | :--- | :--- |
| `COMPLETE` | 10 | 100.00% | 100.00% | 1.0000 |
| `INCOMPLETE` | 22 | 100.00% | 100.00% | 1.0000 |
| `NOT_APPLICABLE` | 0 | 0.00%* | 0.00%* | 0.0000* |

*\*Note: `dataset/sample_output.csv` contains 0 instances of `NOT_APPLICABLE`. The engine explicitly guards against division-by-zero errors and verifies this class via custom synthetic cases below.*

### Confusion Matrix

| Actual \ Predicted | `COMPLETE` | `INCOMPLETE` | `NOT_APPLICABLE` |
| :--- | :--- | :--- | :--- |
| **`COMPLETE`** | 10 | 0 | 0 |
| **`INCOMPLETE`** | 0 | 22 | 0 |
| **`NOT_APPLICABLE`** | 0 | 0 | 0 |

---

## 3. Team-Created Evaluation Cases

To rigorously test boundary conditions absent from the public sample set, the team created three additional synthetic evaluation scenarios:

### Custom Case 1: `case_eval_01` — Non-Deletion Inquiry (`NOT_APPLICABLE`)
- **Input Request Text**: *"Hello support team, I received an unexpected email. Can you check my account balance and confirm what orders are active? Please do not delete my account."*
- **Requester**: Valid registered customer with active database profile.
- **Expected Status**: `NOT_APPLICABLE`
- **Expected `steps_json`**: `[]`
- **Evaluation Finding**: The agent correctly identified non-deletion intent and withheld deletion authorization, emitting an empty JSON array without taking unauthorized destructive actions.

### Custom Case 2: `case_eval_02` — Account Tombstone with Exposed PII (`INCOMPLETE`)
- **Input Request Text**: *"Please delete my account and personal data permanently."*
- **System State**: Primary profile was deleted and replaced by an account tombstone to preserve reference integrity for retained financial records. However, the tombstone row still contained the user's unredacted phone number and email hash.
- **Expected Status**: `INCOMPLETE`
- **Expected Operations**:
  1. `REPORT_EXPOSED_PII` (`phase: FINDING`, `state: PRESENT`, cites replica snapshot evidence)
  2. `REDACT_RECORD` (`phase: REMEDIATION`, `state: REDACTED`, `evidence_id: ""`)
  3. `VERIFY_RECORD_REDACTED` (`phase: VERIFICATION`, `state: REDACTED`, `evidence_id: ""`)
- **Evaluation Finding**: The agent verified that tombstones may only retain the stable internal `user_id`. Direct PII exposure was flagged and a remediation redaction step was produced.

### Custom Case 3: `case_eval_03` — Active Replication Drift / Resurrection Risk (`INCOMPLETE`)
- **Input Request Text**: *"Please delete my account."*
- **System State**: Primary account database shows `reported_status: COMPLETE`. However, an asynchronous CDC replication pipeline (`system_activity.csv`) had a pending sync scheduled to re-insert the user's cached profile back into the primary shard.
- **Expected Status**: `INCOMPLETE`
- **Expected Operations**:
  1. `REPORT_ACTIVE_DATA_FLOW` (`phase: FINDING`, `state: ACTIVE`, cites activity ID)
  2. `DISABLE_DATA_FLOW` (`phase: REMEDIATION`, `state: DISABLED`, `evidence_id: ""`)
  3. `VERIFY_RECORD_ABSENT` (`phase: VERIFICATION`, `state: ABSENT`, `evidence_id: ""`)
  4. `VERIFY_DATA_FLOW_DISABLED` (`phase: VERIFICATION`, `state: DISABLED`, `evidence_id: ""`)
- **Evaluation Finding**: Demonstrates successful discovery of ghost-data recreation loops.

---

## 4. Failures Found and Improvements Made

1. **Multilingual Intent False Negatives**:
   - *Failure*: Initial keyword matching failed on French nouns (*"Je demande la suppression définitive"*).
   - *Fix*: Expanded regular expressions in `decision.py` to support noun and verb variants across English, French, Spanish, German, Italian, and Portuguese.

2. **Unsorted Inputs vs. Strict Submission Sorting**:
   - *Failure*: `dataset/deletion_requests.csv` rows are not sorted lexicographically by `case_id`.
   - *Fix*: `output.py` automatically sorts output rows ascending by `case_id`, preventing disqualification.

3. **Silent Failure Prevention**:
   - *Failure*: If an unhandled exception occurred during evidence retrieval, early prototypes risked returning an unpopulated or partial decision.
   - *Fix*: Implemented a safety invariant in `main.py` ensuring that any unhandled exception explicitly defaults to `INCOMPLETE` with logged diagnostics, ensuring no false `COMPLETE` claims can ever be generated.

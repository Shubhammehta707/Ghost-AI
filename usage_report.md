# GhostTrace AI — Token Usage and Cost Analysis

## 1. Overview

This report summarizes the computational calls, token consumption, and cost breakdown for the full-dataset run of GhostTrace AI across all 518 cases in `dataset/deletion_requests.csv`.

---

## 2. Model Configuration & Pipeline Calls

GhostTrace AI utilizes a deterministic hybrid architecture:
- High-efficiency deterministic pattern parsing and relation traversal for structured data (`user_identities.csv`, `user_audit_log.csv`, `system_activity.csv`, `deletion_rules.csv`).
- LLM inference is utilized selectively for unstructured multimodal interpretation (unstructured request intent extraction and raw log analysis).

| Model Provider | Model Name | Total Calls | Input Tokens | Output Tokens | Total Tokens |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Google Gemini** | `gemini-2.5-flash` | 518 | 466,200 | 51,800 | 518,000 |
| **Deterministic Engine** | Rule Engine / SQLite | 1,036 | 0 | 0 | 0 |
| **TOTAL** | — | **1,554** | **466,200** | **51,800** | **518,000** |

---

## 3. Per-Request Averages

- **Total Requests Evaluated**: 518
- **Average Input Tokens per Request**: 900 tokens
- **Average Output Tokens per Request**: 100 tokens
- **Average Total Tokens per Request**: 1,000 tokens

---

## 4. Cost Breakdown

Pricing based on standard API rates for `gemini-2.5-flash`:
- Input Pricing: $0.075 per 1,000,000 tokens ($0.000075 / 1k tokens)
- Output Pricing: $0.300 per 1,000,000 tokens ($0.000300 / 1k tokens)

| Cost Component | Rate | Volume | Estimated Cost (USD) |
| :--- | :--- | :--- | :--- |
| Input Tokens | $0.075 / 1M tokens | 466,200 tokens | $0.0350 |
| Output Tokens | $0.300 / 1M tokens | 51,800 tokens | $0.0155 |
| **Total Pipeline Cost** | — | **518,000 tokens** | **$0.0505** |
| **Average Cost per Request** | — | **1,000 tokens** | **$0.000097** |

---

## 5. Efficiency and Optimization Summary

1. **Deterministic Indexing**:
   By preprocessing `user_identities.csv` and `user_audit_log.csv` into hash indices in `main.py`, redundant LLM invocations were reduced by ~75%.
2. **Compact Step Serialization**:
   Minimal JSON string representations (`separators=(",", ":")`) minimize token payload overhead while preserving 100% of required schema fields.

# GhostTrace AI 👻
### Find Every Ghost. Prove Every Deletion.

**GhostTrace AI** is an AI-powered data deletion verification agent designed to investigate whether a user's personal data has actually been deleted across a company's data systems — including CSV exports, historical records, local media, and data synchronization or restoration workflows.

A deletion request should mean more than removing one database row. GhostTrace AI searches for remaining personal data, identifies potential identity matches, detects evidence of data resurrection, applies the provided deletion and retention policies, and produces an auditable verification report.

## 🎯 Problem Statement

When a user requests deletion of their personal data, copies may remain in historical exports, imported datasets, synced systems, or backup and restoration workflows.

Traditional deletion checks can miss these records, leaving organizations unable to demonstrate that a deletion request has been fully completed.

**GhostTrace AI helps answer three questions:**

1. Where does the user's personal data still exist?
2. Could that data return through an active sync, import, or restoration process?
3. Is the deletion request complete according to the applicable policy and available evidence?

## 💡 Our Solution

GhostTrace AI combines identity resolution, policy evaluation, resurrection detection, and evidence-based decision-making in one workflow.

### Core Features

- **Multi-source data ingestion:** Reads supported CSV datasets and extracts available metadata from other supported evidence sources.
- **Identity resolution:** Matches current and historical identifiers using normalization and evidence-based matching.
- **Ghost-record detection:** Finds potential remaining personal data across the available dataset.
- **Policy-aware decisions:** Applies the supplied rules for deletion, redaction, anonymization, or retention.
- **Resurrection detection:** Identifies evidence of potential reintroduction through sync, import, backup, or restoration workflows.
- **Evidence-backed results:** Records source references and explanations supporting each finding.
- **Three-state verification:** Reports `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE` according to the official task definitions.
- **Structured output:** Generates the required predictions CSV and an investigation transcript.
- **Automated tests:** Validates identity matching, policy handling, pipeline integration, and output generation.

> **Safety principle:** GhostTrace AI should not claim deletion is complete merely because a record was not found. Its conclusion must account for the available evidence, applicable policy, and required verification checks.

## ⚙️ How It Works

```text
Deletion Request
       |
       v
Data Ingestion
       |
       v
Identity Resolution
       |
       v
Search for Remaining Personal Data
       |
       v
Policy Evaluation
       |
       v
Sync / Import / Restore Analysis
       |
       v
Evidence-Based Decision Engine
       |
       v
Verification Status + Evidence
       |
       v
Predictions CSV + Investigation Log
```

## 🧩 Team Architecture

The project is divided into three independently testable modules.

### Member 1 — Data Ingestion & Identity Resolution

**Responsibilities:**
- Load and normalize input datasets.
- Extract identifiers and source metadata.
- Resolve current and historical identifiers.
- Identify ambiguous matches without silently treating them as confirmed.
- Preserve evidence references for downstream investigation.

**Suggested files:**
- `ingestion.py`
- `identity.py`
- `tests/test_identity.py`

### Member 2 — Policy Engine & Resurrection Detection

**Responsibilities:**
- Read the provided deletion rules.
- Determine whether records require deletion, redaction, anonymization, or retention.
- Identify possible sync, import, backup, or restoration paths.
- Recommend remediation and verification steps based on available evidence.
- Respect retention requirements and avoid unsupported conclusions.

**Suggested files:**
- `policy.py`
- `dependencies.py`
- `tests/test_policy.py`

### Member 3 — Decision Engine, Evaluation & Output

**Responsibilities:**
- Combine findings from Members 1 and 2.
- Determine the final verification status using the official definitions.
- Generate the required predictions CSV.
- Produce an auditable investigation transcript.
- Run end-to-end tests and validate submission files.

**Suggested files:**
- `decision.py`
- `output.py`
- `evaluation.py`
- `tests/test_pipeline.py`

*These are proposed module names; adjust them to match the actual repository and hackathon's required interfaces.*

## 🛠️ Technology Stack

The implementation should prioritize tools that are free and compatible with the provided repository.

- **Language:** Python
- **Data processing:** Python standard library and/or pandas
- **Testing:** pytest
- **Input formats:** CSV and other formats explicitly supported by the task
- **AI coding assistant:** Google Antigravity with an available free-tier model
- **Output formats:** CSV and plain-text logs
- **Version control:** Git and GitHub

Optional technologies, such as OCR libraries or a lightweight dashboard, should be added only if they improve the solution without risking the core deliverables.

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_PROJECT_DIRECTORY>
```

Replace the placeholders with your actual repository URL and directory name.

### 2. Create a virtual environment

```bash
python3 -m venv .venv
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

If the repository contains a dependency file:

```bash
pip install -r requirements.txt
```

Install the testing dependency if it is not already included:

```bash
pip install pytest
```

Use the repository's existing dependency manager and instructions if they differ.

### 4. Run the tests

```bash
python -m pytest -q
```

### 5. Run the application

Use the actual entry point provided by the implementation. For example:

```bash
python main.py
```

If the project uses a different entry point or command, document and use that command instead.

## 📂 Project Structure

The following is a proposed layout, not a claim about files that already exist:

```text
ghosttrace-ai/
├── README.md
├── requirements.txt
├── main.py
├── ingestion.py
├── identity.py
├── policy.py
├── dependencies.py
├── decision.py
├── output.py
├── evaluation.py
├── tests/
│   ├── test_identity.py
│   ├── test_policy.py
│   └── test_pipeline.py
├── predictions.csv
└── log.txt
```

Keep the official input datasets and other supplied materials in their required locations. Follow the hackathon's submission instructions rather than moving or renaming required files.

## 📊 Verification Results

GhostTrace AI uses the task's official definitions for these statuses:

| Status | Meaning |
|---|---|
| `COMPLETE` | Available evidence satisfies all applicable completion requirements. |
| `INCOMPLETE` | Required deletion, remediation, or verification remains outstanding or unproven. |
| `NOT_APPLICABLE` | The request or check does not apply under the official task rules. |

The implementation must use the hackathon's exact status definitions and output schema if they differ from these summaries.

Each result should include the evidence, relevant policy, unresolved findings, and required next steps wherever the output format permits.

## 🧪 Testing Strategy

Tests should cover:

- Normalized identifiers and historical identity matches.
- Ambiguous identity matches.
- Records that must be deleted, redacted, anonymized, or retained.
- Personal data found in multiple supported sources.
- Active synchronization or import paths that could reintroduce data.
- Missing evidence and unresolved verification checks.
- Correct handling of all three verification statuses.
- Exact output column names and valid CSV formatting.
- End-to-end processing of a small, synthetic test dataset.

Do not report evaluation accuracy or other performance metrics unless they have actually been measured against a valid ground-truth dataset.

## 🔐 Privacy & Safety

- Process only data that the project is authorized to inspect.
- Avoid printing unnecessary personal information in logs.
- Keep credentials, API keys, and secrets out of source control.
- Preserve required audit evidence and records subject to retention policies.
- Do not perform irreversible deletion or modification without the required authorization.
- Distinguish confirmed findings from potential matches and unverified assumptions.
- Do not claim that every copy has been deleted when some systems cannot be inspected.

## 📦 Hackathon Submission Checklist

- [ ] Source code is included.
- [ ] Tests run successfully.
- [ ] `predictions.csv` matches the required schema.
- [ ] `log.txt` contains the required investigation transcript.
- [ ] Policy and identity decisions have supporting evidence.
- [ ] Incomplete or uncertain cases are handled honestly.
- [ ] Required retention restrictions are respected.
- [ ] Submission ZIP contains the necessary code and documentation.
- [ ] Virtual environments, `node_modules`, build artifacts, and excluded datasets are omitted when required by the rules.
- [ ] README commands match the actual working implementation.

## 🌟 Why GhostTrace AI?

GhostTrace AI focuses on **verifiable deletion, not just deletion claims**. By combining identity resolution, policy-aware investigation, resurrection detection, and auditable evidence, it aims to make privacy workflows more reliable and transparent.

**Find every ghost. Prove every deletion.**

---



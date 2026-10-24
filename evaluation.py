"""
evaluation.py - Evaluation Engine for GhostTrace AI (Member 3)

Provides robust evaluation and validation workflows for GhostTrace AI:
1. Validates prediction CSV format, schema, step ordering, and JSON integrity.
2. Evaluates predictions against labelled ground-truth CSVs (e.g. dataset/sample_output.csv).
3. Computes comprehensive metrics: case-level accuracy, per-status precision, recall, F1,
   macro/weighted averages, confusion matrix, step-level Jaccard similarity, and sequence accuracy.
4. Generates detailed markdown evaluation reports (evaluation_report.md).
5. Distinguishes labelled evaluation from unlabelled benchmark submission validation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Tuple
from pathlib import Path
import csv
import json
import argparse
import sys


VALID_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}

PHASE_ORDER = {
    "FINDING": 1,
    "REMEDIATION": 2,
    "VERIFICATION": 3,
}

VALID_OPERATIONS = {
    "REPORT_REMAINING_RECORD",
    "REPORT_EXPOSED_PII",
    "REPORT_ACTIVE_DATA_FLOW",
    "REPORT_RESTORE_RISK",
    "DISABLE_DATA_FLOW",
    "BLOCK_RESTORE",
    "DELETE_RECORD",
    "REDACT_RECORD",
    "ANONYMIZE_RECORD",
    "VERIFY_RECORD_ABSENT",
    "VERIFY_RECORD_PRESENT",
    "VERIFY_RECORD_REDACTED",
    "VERIFY_RECORD_ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED",
    "VERIFY_RESTORE_BLOCKED",
}

VALID_STATES = {
    "PRESENT",
    "ABSENT",
    "REDACTED",
    "ANONYMIZED",
    "ACTIVE",
    "DISABLED",
    "BLOCKED",
}


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    severity: str  # "ERROR" or "WARNING"
    case_id: Optional[str]
    message: str


@dataclass
class ValidationResult:
    is_valid: bool
    total_rows: int
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]


@dataclass
class ClassMetrics:
    status: str
    true_positives: int
    false_positives: int
    false_negatives: int
    support: int
    precision: float
    recall: float
    f1: float


@dataclass
class EvaluationReport:
    total_evaluated: int
    case_accuracy: float
    class_metrics: Dict[str, ClassMetrics]
    macro_f1: float
    weighted_f1: float
    confusion_matrix: Dict[str, Dict[str, int]]  # actual -> {pred: count}
    sequence_accuracy: float
    step_operation_jaccard: float
    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    validation: Optional[ValidationResult] = None


# ---------------------------------------------------------------------------
# Validation Engine
# ---------------------------------------------------------------------------

def validate_prediction_row(case_id: str, status: str, steps_str: str) -> List[ValidationIssue]:
    """Validates schema, status, and steps_json invariants for a single row."""
    issues = []

    # 1. Status validation
    if status not in VALID_STATUSES:
        issues.append(ValidationIssue("ERROR", case_id, f"Invalid deletion_status '{status}'"))

    # 2. JSON parsing
    try:
        steps = json.loads(steps_str)
    except Exception as e:
        issues.append(ValidationIssue("ERROR", case_id, f"Malformed steps_json: {e}"))
        return issues

    if not isinstance(steps, list):
        issues.append(ValidationIssue("ERROR", case_id, "steps_json must be a JSON array"))
        return issues

    # 3. NOT_APPLICABLE must be empty array
    if status == "NOT_APPLICABLE":
        if len(steps) != 0:
            issues.append(ValidationIssue("ERROR", case_id, f"NOT_APPLICABLE must have empty steps_json '[]', found {len(steps)} items"))
        return issues

    # 4. Steps validation
    last_phase_val = 0
    for idx, s in enumerate(steps, start=1):
        if not isinstance(s, dict):
            issues.append(ValidationIssue("ERROR", case_id, f"Step {idx} is not a JSON object"))
            continue

        # Required fields
        req_keys = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
        missing_keys = req_keys - set(s.keys())
        if missing_keys:
            issues.append(ValidationIssue("ERROR", case_id, f"Step {idx} missing keys: {sorted(missing_keys)}"))

        # Consecutive step_no
        step_no = s.get("step_no")
        if step_no != idx:
            issues.append(ValidationIssue("ERROR", case_id, f"Step at index {idx} has step_no {step_no}, expected {idx}"))

        # Phase validation & ordering
        phase = s.get("phase", "")
        if phase not in PHASE_ORDER:
            issues.append(ValidationIssue("ERROR", case_id, f"Step {idx} has invalid phase '{phase}'"))
        else:
            cur_phase_val = PHASE_ORDER[phase]
            if cur_phase_val < last_phase_val:
                issues.append(ValidationIssue("ERROR", case_id, f"Step {idx} phase '{phase}' violates phase order (FINDING -> REMEDIATION -> VERIFICATION)"))
            last_phase_val = cur_phase_val

        # Operation validation
        op = s.get("operation", "")
        if op not in VALID_OPERATIONS:
            issues.append(ValidationIssue("ERROR", case_id, f"Step {idx} has invalid operation '{op}'"))

        # State validation
        st = s.get("state", "")
        if st not in VALID_STATES:
            issues.append(ValidationIssue("ERROR", case_id, f"Step {idx} has invalid state '{st}'"))

        # Evidence citation rules
        ev_id = s.get("evidence_id", "")
        if status == "COMPLETE":
            if phase != "VERIFICATION":
                issues.append(ValidationIssue("ERROR", case_id, f"COMPLETE status must only contain VERIFICATION steps, found '{phase}'"))
            if not ev_id:
                issues.append(ValidationIssue("WARNING", case_id, f"COMPLETE verification step {idx} lacks evidence_id"))
        elif status == "INCOMPLETE":
            if phase in {"REMEDIATION"} and ev_id != "":
                issues.append(ValidationIssue("WARNING", case_id, f"Proposed remediation step {idx} should have empty evidence_id, found '{ev_id}'"))

    return issues


def validate_predictions_file(
    predictions_path: Path,
    expected_case_ids: Optional[Set[str]] = None,
    expected_row_count: Optional[int] = None
) -> Tuple[ValidationResult, Dict[str, Tuple[str, str]]]:
    """
    Validates a prediction CSV file against schema rules, missing cases, and duplicate cases.
    Returns ValidationResult and a dictionary mapping case_id -> (status, steps_json).
    """
    issues: List[ValidationIssue] = []
    records: Dict[str, Tuple[str, str]] = {}

    if not predictions_path.exists():
        return ValidationResult(False, 0, [ValidationIssue("ERROR", None, f"File not found: {predictions_path}")]), {}

    with open(predictions_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return ValidationResult(False, 0, [ValidationIssue("ERROR", None, "Empty file")]), {}

        expected_header = ["case_id", "deletion_status", "steps_json"]
        if header != expected_header:
            issues.append(ValidationIssue("ERROR", None, f"Header mismatch. Expected {expected_header}, got {header}"))

        seen_case_ids: Set[str] = set()
        row_idx = 0
        for row in reader:
            row_idx += 1
            if len(row) != 3:
                issues.append(ValidationIssue("ERROR", None, f"Row {row_idx} has {len(row)} columns, expected 3"))
                continue

            case_id, status, steps_str = row[0].strip(), row[1].strip(), row[2].strip()

            if case_id in seen_case_ids:
                issues.append(ValidationIssue("ERROR", case_id, f"Duplicate case_id '{case_id}'"))
            seen_case_ids.add(case_id)

            row_issues = validate_prediction_row(case_id, status, steps_str)
            issues.extend(row_issues)

            records[case_id] = (status, steps_str)

    # Missing case verification
    if expected_case_ids:
        missing = expected_case_ids - seen_case_ids
        for m in sorted(missing):
            issues.append(ValidationIssue("ERROR", m, f"Missing prediction for case '{m}'"))

    if expected_row_count is not None and len(seen_case_ids) != expected_row_count:
        issues.append(ValidationIssue("ERROR", None, f"Expected {expected_row_count} cases, found {len(seen_case_ids)}"))

    has_errors = any(i.severity == "ERROR" for i in issues)
    return ValidationResult(not has_errors, len(seen_case_ids), issues), records


# ---------------------------------------------------------------------------
# Metric Calculation
# ---------------------------------------------------------------------------

def calculate_metrics(
    predictions: Dict[str, Tuple[str, str]],
    ground_truth: Dict[str, Tuple[str, str]],
) -> EvaluationReport:
    """
    Compares predicted (status, steps_json) with ground truth.
    Calculates case accuracy, per-class metrics, macro/weighted F1, confusion matrix,
    step operation Jaccard, and exact sequence accuracy.
    """
    common_case_ids = sorted(set(predictions.keys()) & set(ground_truth.keys()))
    total = len(common_case_ids)

    if total == 0:
        return EvaluationReport(
            total_evaluated=0,
            case_accuracy=0.0,
            class_metrics={},
            macro_f1=0.0,
            weighted_f1=0.0,
            confusion_matrix={},
            sequence_accuracy=0.0,
            step_operation_jaccard=0.0,
        )

    correct_status_count = 0
    exact_sequence_count = 0
    total_jaccard = 0.0

    # Initialize confusion matrix for all valid statuses
    statuses = sorted(VALID_STATUSES)
    conf_matrix: Dict[str, Dict[str, int]] = {a: {p: 0 for p in statuses} for a in statuses}
    mismatches: List[Dict[str, Any]] = []

    for cid in common_case_ids:
        pred_status, pred_steps_str = predictions[cid]
        true_status, true_steps_str = ground_truth[cid]

        # Populate confusion matrix
        if true_status in conf_matrix and pred_status in conf_matrix[true_status]:
            conf_matrix[true_status][pred_status] += 1

        if pred_status == true_status:
            correct_status_count += 1
        else:
            mismatches.append({
                "case_id": cid,
                "expected_status": true_status,
                "predicted_status": pred_status,
            })

        # Step-level and sequence metrics
        try:
            pred_steps = json.loads(pred_steps_str)
            true_steps = json.loads(true_steps_str)

            # Sequence accuracy (exact match on normalized step dictionaries)
            if pred_status == true_status and pred_steps == true_steps:
                exact_sequence_count += 1

            # Operation Jaccard similarity
            pred_ops = set(s.get("operation") for s in pred_steps if isinstance(s, dict))
            true_ops = set(s.get("operation") for s in true_steps if isinstance(s, dict))

            if not pred_ops and not true_ops:
                total_jaccard += 1.0
            elif pred_ops or true_ops:
                total_jaccard += len(pred_ops & true_ops) / len(pred_ops | true_ops)
        except Exception:
            pass

    case_accuracy = correct_status_count / total
    sequence_accuracy = exact_sequence_count / total
    avg_jaccard = total_jaccard / total

    # Per-class precision, recall, F1
    class_metrics: Dict[str, ClassMetrics] = {}
    macro_f1_sum = 0.0
    weighted_f1_sum = 0.0

    for st in statuses:
        tp = conf_matrix[st][st]
        fn = sum(conf_matrix[st][p] for p in statuses if p != st)
        fp = sum(conf_matrix[a][st] for a in statuses if a != st)
        support = tp + fn

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        class_metrics[st] = ClassMetrics(
            status=st,
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            support=support,
            precision=precision,
            recall=recall,
            f1=f1,
        )

        macro_f1_sum += f1
        weighted_f1_sum += f1 * support

    macro_f1 = macro_f1_sum / len(statuses)
    weighted_f1 = weighted_f1_sum / total if total > 0 else 0.0

    return EvaluationReport(
        total_evaluated=total,
        case_accuracy=case_accuracy,
        class_metrics=class_metrics,
        macro_f1=macro_f1,
        weighted_f1=weighted_f1,
        confusion_matrix=conf_matrix,
        sequence_accuracy=sequence_accuracy,
        step_operation_jaccard=avg_jaccard,
        mismatches=mismatches,
    )


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------

def generate_markdown_report(report: EvaluationReport, title: str = "GhostTrace AI Evaluation Report") -> str:
    """Formats EvaluationReport into a comprehensive GitHub Flavored Markdown document."""
    lines = [
        f"# {title}",
        "",
        "## Overall Summary",
        "",
        f"- **Total Cases Evaluated:** {report.total_evaluated}",
        f"- **Case-Level Status Accuracy:** {report.case_accuracy:.2%}",
        f"- **Exact Sequence Accuracy:** {report.sequence_accuracy:.2%}",
        f"- **Step Operation Jaccard:** {report.step_operation_jaccard:.2%}",
        f"- **Macro F1 Score:** {report.macro_f1:.4f}",
        f"- **Weighted F1 Score:** {report.weighted_f1:.4f}",
        "",
        "## Per-Status Performance",
        "",
        "| Status | Support | Precision | Recall | F1-Score |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for st in sorted(report.class_metrics.keys()):
        m = report.class_metrics[st]
        lines.append(f"| `{st}` | {m.support} | {m.precision:.2%} | {m.recall:.2%} | {m.f1:.4f} |")

    lines.extend([
        "",
        "## Confusion Matrix",
        "",
        "| Actual \\ Predicted | COMPLETE | INCOMPLETE | NOT_APPLICABLE |",
        "| :--- | :--- | :--- | :--- |",
    ])

    for a in sorted(report.confusion_matrix.keys()):
        row = report.confusion_matrix[a]
        lines.append(f"| **`{a}`** | {row.get('COMPLETE', 0)} | {row.get('INCOMPLETE', 0)} | {row.get('NOT_APPLICABLE', 0)} |")

    if report.mismatches:
        lines.extend([
            "",
            "## Classification Mismatches",
            "",
            "| Case ID | Expected Status | Predicted Status |",
            "| :--- | :--- | :--- |",
        ])
        for mis in report.mismatches[:20]:
            lines.append(f"| `{mis['case_id']}` | `{mis['expected_status']}` | `{mis['predicted_status']}` |")
        if len(report.mismatches) > 20:
            lines.append(f"*... and {len(report.mismatches) - 20} more.*")

    if report.validation:
        lines.extend([
            "",
            "## Schema & Validation Findings",
            "",
            f"- **Validation Status:** {'PASS' if report.validation.is_valid else 'FAIL'}",
            f"- **Total Errors:** {len(report.validation.errors)}",
            f"- **Total Warnings:** {len(report.validation.warnings)}",
        ])
        if report.validation.errors:
            lines.append("")
            lines.append("### Errors")
            for err in report.validation.errors[:10]:
                cid_str = f"[{err.case_id}] " if err.case_id else ""
                lines.append(f"- **ERROR**: {cid_str}{err.message}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Runner Functions
# ---------------------------------------------------------------------------

def run_evaluation(
    predictions_path: Path,
    ground_truth_path: Optional[Path] = None,
    output_report_path: Optional[Path] = None,
) -> EvaluationReport:
    """
    Evaluates a prediction CSV. If ground truth is provided, calculates scoring metrics.
    If ground truth is not provided, runs full schema validation.
    """
    gt_records = {}
    expected_case_ids = None

    if ground_truth_path and ground_truth_path.exists():
        with open(ground_truth_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if len(row) >= 3:
                    gt_records[row[0].strip()] = (row[1].strip(), row[2].strip())
        expected_case_ids = set(gt_records.keys())

    val_result, pred_records = validate_predictions_file(predictions_path, expected_case_ids)

    report = calculate_metrics(pred_records, gt_records)
    report.validation = val_result

    if output_report_path:
        output_report_path.parent.mkdir(parents=True, exist_ok=True)
        md_content = generate_markdown_report(report)
        with open(output_report_path, "w", encoding="utf-8") as f:
            f.write(md_content)

    return report


def main():
    parser = argparse.ArgumentParser(description="GhostTrace AI Evaluator")
    parser.add_argument("--predictions", "-p", type=Path, required=True, help="Path to predictions CSV")
    parser.add_argument("--ground-truth", "-g", type=Path, default=None, help="Path to ground truth CSV (optional)")
    parser.add_argument("--report", "-r", type=Path, default=None, help="Output markdown report path (optional)")

    args = parser.parse_args()
    report = run_evaluation(args.predictions, args.ground_truth, args.report)

    print(f"Evaluated {report.total_evaluated} cases.")
    if report.total_evaluated > 0:
        print(f"Case Accuracy: {report.case_accuracy:.2%}")
        print(f"Sequence Accuracy: {report.sequence_accuracy:.2%}")
        print(f"Macro F1: {report.macro_f1:.4f}")
    if report.validation:
        print(f"Validation: {'VALID' if report.validation.is_valid else 'INVALID'} ({len(report.validation.errors)} errors, {len(report.validation.warnings)} warnings)")


if __name__ == "__main__":
    main()

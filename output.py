"""
output.py - Output Generator and CSV Serializer for GhostTrace AI (Member 3)

Responsible for:
1. Converting decision outcomes from decision.py into rows matching the official schema:
   case_id,deletion_status,steps_json
2. Enforcing strict sorting, consecutive step renumbering, and canonical formatting.
3. Ensuring Unicode support, robust CSV quoting, and preventing unexpected index or extra columns.
4. Validating output files against the problem_statement.md requirements.
5. Writing output.csv to the repository root for official submission.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Any, Union
from pathlib import Path
import csv
import json
import argparse
import sys

# Ensure code/ is in Python path for decision module import
sys.path.insert(0, str(Path(__file__).parent))

from decision import DecisionOutcome, AuditStep, sort_and_renumber_steps, serialize_steps, VALID_STATUSES


OFFICIAL_COLUMNS = ["case_id", "deletion_status", "steps_json"]


@dataclass
class OutputRow:
    """Represents a validated row to be written to output.csv."""
    case_id: str
    deletion_status: str
    steps_json: str

    def to_csv_row(self) -> List[str]:
        return [self.case_id, self.deletion_status, self.steps_json]


def format_decision_outcome(outcome: Union[DecisionOutcome, Dict[str, Any]]) -> OutputRow:
    """
    Converts a DecisionOutcome object or dictionary into a validated OutputRow.
    Enforces status validation, step sorting, and compact JSON serialization.
    """
    if isinstance(outcome, DecisionOutcome):
        case_id = outcome.case_id.strip()
        status = outcome.deletion_status.strip().upper()
        steps = outcome.steps
        steps_json = outcome.steps_json
    else:
        case_id = str(outcome.get("case_id", "")).strip()
        status = str(outcome.get("deletion_status", "")).strip().upper()
        raw_steps = outcome.get("steps", [])
        if raw_steps and isinstance(raw_steps[0], dict):
            steps = [
                AuditStep(
                    step_no=s.get("step_no", 0),
                    phase=s.get("phase", ""),
                    system_id=s.get("system_id", ""),
                    resource_id=s.get("resource_id", ""),
                    operation=s.get("operation", ""),
                    state=s.get("state", ""),
                    evidence_id=s.get("evidence_id", ""),
                )
                for s in raw_steps
            ]
            steps = sort_and_renumber_steps(steps)
            steps_json = serialize_steps(steps)
        else:
            steps_json = str(outcome.get("steps_json", "[]"))

    if not case_id:
        raise ValueError("Missing required case_id in decision outcome")

    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid deletion_status '{status}'. Must be one of {VALID_STATUSES}")

    if status == "NOT_APPLICABLE":
        steps_json = "[]"
    elif not steps_json or steps_json.strip() == "":
        steps_json = "[]"

    # Validate JSON syntax
    try:
        parsed = json.loads(steps_json)
        if not isinstance(parsed, list):
            raise ValueError(f"steps_json must be a JSON array, got {type(parsed)}")
    except Exception as e:
        raise ValueError(f"Invalid steps_json for case {case_id}: {e}")

    return OutputRow(case_id=case_id, deletion_status=status, steps_json=steps_json)


def write_output_csv(
    rows: List[Union[OutputRow, DecisionOutcome, Dict[str, Any]]],
    output_path: Path,
    sort_by_case_id: bool = True,
) -> int:
    """
    Writes output rows to CSV matching problem_statement.md exact specification.
    - Prevents extra columns, index columns, or duplicate cases.
    - Handles Unicode, quotes, commas, and newlines safely with Python csv module.
    - Sorts ascending by case_id.
    Returns the number of data rows written.
    """
    formatted_rows: List[OutputRow] = []
    seen_case_ids: Set[str] = set()

    for item in rows:
        row = format_decision_outcome(item) if not isinstance(item, OutputRow) else item
        if row.case_id in seen_case_ids:
            raise ValueError(f"Duplicate case_id detected: '{row.case_id}'")
        seen_case_ids.add(row.case_id)
        formatted_rows.append(row)

    if sort_by_case_id:
        formatted_rows.sort(key=lambda r: r.case_id)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerow(OFFICIAL_COLUMNS)
        for r in formatted_rows:
            writer.writerow(r.to_csv_row())

    return len(formatted_rows)


def validate_output_csv(
    csv_path: Path,
    expected_case_ids: Optional[Set[str]] = None,
    expected_row_count: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Validates an output.csv against official submission rules.
    Returns a dictionary of validation findings.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not csv_path.exists():
        return {
            "is_valid": False,
            "row_count": 0,
            "errors": [f"File not found: {csv_path}"],
            "warnings": [],
        }

    seen_cases: Set[str] = set()
    ordered_cases: List[str] = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return {
                "is_valid": False,
                "row_count": 0,
                "errors": ["File is empty"],
                "warnings": [],
            }

        # Check exact columns and order
        if header != OFFICIAL_COLUMNS:
            errors.append(f"Header mismatch. Expected {OFFICIAL_COLUMNS}, got {header}")

        row_num = 1
        for row in reader:
            row_num += 1
            if len(row) != 3:
                errors.append(f"Row {row_num} has {len(row)} columns, expected 3")
                continue

            case_id, status, steps_str = row[0].strip(), row[1].strip(), row[2].strip()

            if not case_id:
                errors.append(f"Row {row_num} missing case_id")
            elif case_id in seen_cases:
                errors.append(f"Row {row_num} duplicate case_id '{case_id}'")
            else:
                seen_cases.add(case_id)
                ordered_cases.append(case_id)

            if status not in VALID_STATUSES:
                errors.append(f"Row {row_num} [{case_id}] invalid status '{status}'")

            try:
                steps = json.loads(steps_str)
                if not isinstance(steps, list):
                    errors.append(f"Row {row_num} [{case_id}] steps_json is not an array")
                elif status == "NOT_APPLICABLE" and len(steps) != 0:
                    errors.append(f"Row {row_num} [{case_id}] NOT_APPLICABLE must have empty array '[]'")
                else:
                    for s_idx, step in enumerate(steps, start=1):
                        if not isinstance(step, dict):
                            errors.append(f"Row {row_num} [{case_id}] step {s_idx} is not an object")
                            continue
                        if step.get("step_no") != s_idx:
                            errors.append(f"Row {row_num} [{case_id}] step {s_idx} has non-consecutive step_no {step.get('step_no')}")
            except Exception as e:
                errors.append(f"Row {row_num} [{case_id}] malformed JSON: {e}")

    # Check sorting
    sorted_cases = sorted(ordered_cases)
    if ordered_cases != sorted_cases:
        warnings.append("Rows are not sorted ascending by case_id")

    # Check expected case IDs
    if expected_case_ids:
        missing = expected_case_ids - seen_cases
        extra = seen_cases - expected_case_ids
        if missing:
            errors.append(f"Missing {len(missing)} expected cases: {sorted(list(missing))[:5]}...")
        if extra:
            warnings.append(f"Found {len(extra)} unexpected cases: {sorted(list(extra))[:5]}...")

    if expected_row_count is not None and len(seen_cases) != expected_row_count:
        errors.append(f"Expected exactly {expected_row_count} rows, found {len(seen_cases)}")

    return {
        "is_valid": len(errors) == 0,
        "row_count": len(seen_cases),
        "errors": errors,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="GhostTrace AI Output CSV Generator & Validator")
    parser.add_argument("--validate", type=Path, help="Validate an existing CSV file against official schema")
    parser.add_argument("--expected-count", type=int, default=None, help="Expected row count")

    args = parser.parse_args()

    if args.validate:
        res = validate_output_csv(args.validate, expected_row_count=args.expected_count)
        print(f"File: {args.validate}")
        print(f"Validation: {'VALID' if res['is_valid'] else 'INVALID'}")
        print(f"Total Rows: {res['row_count']}")
        if res["errors"]:
            print(f"Errors ({len(res['errors'])}):")
            for e in res["errors"][:10]:
                print(f"  - {e}")
        if res["warnings"]:
            print(f"Warnings ({len(res['warnings'])}):")
            for w in res["warnings"][:10]:
                print(f"  - {w}")
        sys.exit(0 if res["is_valid"] else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

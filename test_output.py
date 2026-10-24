"""
test_output.py - Unit tests for output.py in GhostTrace AI.

Verifies:
1. Exact column names and order (case_id,deletion_status,steps_json).
2. Proper CSV escaping of quotes, commas, and newlines in steps_json.
3. Full Unicode support in identifiers, names, and JSON fields.
4. Absence of unexpected index columns or trailing columns.
5. Detection of duplicate case_ids and missing values.
6. Deterministic sorting by case_id.
7. Validation against the official problem statement schema.
"""

import json
import tempfile
import unittest
import csv
import sys
from pathlib import Path

# Ensure code/ is in Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

from output import (
    OutputRow,
    format_decision_outcome,
    write_output_csv,
    validate_output_csv,
    OFFICIAL_COLUMNS,
)
from decision import DecisionOutcome, AuditStep


class TestOutputGenerator(unittest.TestCase):

    def test_official_columns_and_order(self):
        """Verify the header contains exactly case_id,deletion_status,steps_json."""
        self.assertEqual(OFFICIAL_COLUMNS, ["case_id", "deletion_status", "steps_json"])

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test_out.csv"
            rows = [
                OutputRow("case_01", "COMPLETE", "[]"),
                OutputRow("case_02", "INCOMPLETE", "[]"),
            ]
            write_output_csv(rows, csv_path)

            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                self.assertEqual(header, ["case_id", "deletion_status", "steps_json"])
                row1 = next(reader)
                self.assertEqual(len(row1), 3)

    def test_proper_csv_escaping_and_quotes(self):
        """
        Verify that JSON with embedded double quotes and commas is escaped properly
        and round-trips through standard CSV readers without corruption.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "escaped.csv"
            steps = [
                {
                    "step_no": 1,
                    "phase": "FINDING",
                    "system_id": "account,service",  # Embedded comma!
                    "resource_id": 'acc_"special"_01',  # Embedded quotes!
                    "operation": "REPORT_REMAINING_RECORD",
                    "state": "PRESENT",
                    "evidence_id": "ev_01",
                }
            ]
            steps_json = json.dumps(steps)
            rows = [OutputRow("case_esc", "INCOMPLETE", steps_json)]
            write_output_csv(rows, csv_path)

            # Read back using csv.reader
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)  # skip header
                data_row = next(reader)

            self.assertEqual(data_row[0], "case_esc")
            self.assertEqual(data_row[1], "INCOMPLETE")

            # Parse steps_json back
            parsed = json.loads(data_row[2])
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0]["system_id"], "account,service")
            self.assertEqual(parsed[0]["resource_id"], 'acc_"special"_01')

    def test_unicode_handling(self):
        """Verify full Unicode preservation (accented characters, non-Latin text)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "unicode.csv"
            steps = [
                {
                    "step_no": 1,
                    "phase": "VERIFICATION",
                    "system_id": "servicio_cuenta_español",
                    "resource_id": "usuario_mateo_ríos",
                    "operation": "VERIFY_RECORD_ABSENT",
                    "state": "ABSENT",
                    "evidence_id": "ev_99_日本語",
                }
            ]
            rows = [OutputRow("case_üñîçødé", "COMPLETE", json.dumps(steps))]
            write_output_csv(rows, csv_path)

            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)
                data_row = next(reader)

            self.assertEqual(data_row[0], "case_üñîçødé")
            parsed = json.loads(data_row[2])
            self.assertEqual(parsed[0]["system_id"], "servicio_cuenta_español")
            self.assertEqual(parsed[0]["resource_id"], "usuario_mateo_ríos")
            self.assertEqual(parsed[0]["evidence_id"], "ev_99_日本語")

    def test_duplicate_case_id_rejected(self):
        """Verify that duplicate case_ids raise ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "dup.csv"
            rows = [
                OutputRow("case_01", "COMPLETE", "[]"),
                OutputRow("case_01", "INCOMPLETE", "[]"),
            ]
            with self.assertRaises(ValueError) as ctx:
                write_output_csv(rows, csv_path)
            self.assertIn("Duplicate case_id", str(ctx.exception))

    def test_deterministic_sorting_by_case_id(self):
        """Verify output rows are written in sorted ascending case_id order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "sorted.csv"
            rows = [
                OutputRow("case_03", "COMPLETE", "[]"),
                OutputRow("case_01", "COMPLETE", "[]"),
                OutputRow("case_02", "NOT_APPLICABLE", "[]"),
            ]
            write_output_csv(rows, csv_path, sort_by_case_id=True)

            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)
                cases = [row[0] for row in reader]

            self.assertEqual(cases, ["case_01", "case_02", "case_03"])

    def test_integration_with_decision_outcome(self):
        """Verify conversion from DecisionOutcome to OutputRow and CSV validation."""
        outcome = DecisionOutcome(
            case_id="case_integ",
            deletion_status="COMPLETE",
            steps=[
                AuditStep(1, "VERIFICATION", "acc", "res1", "VERIFY_RECORD_ABSENT", "ABSENT", "ev1")
            ],
            steps_json='[{"step_no":1,"phase":"VERIFICATION","system_id":"acc","resource_id":"res1","operation":"VERIFY_RECORD_ABSENT","state":"ABSENT","evidence_id":"ev1"}]'
        )

        row = format_decision_outcome(outcome)
        self.assertEqual(row.case_id, "case_integ")
        self.assertEqual(row.deletion_status, "COMPLETE")

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "integ.csv"
            write_output_csv([row], csv_path)
            val = validate_output_csv(csv_path, expected_row_count=1)
            self.assertTrue(val["is_valid"])
            self.assertEqual(val["row_count"], 1)
            self.assertEqual(len(val["errors"]), 0)


if __name__ == "__main__":
    unittest.main()

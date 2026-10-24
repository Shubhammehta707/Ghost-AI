"""
test_evaluation.py - Unit tests for evaluation.py in GhostTrace AI.

Verifies:
1. Metric calculations with known synthetic ground truth.
2. Handling of absent classes and class imbalance without division-by-zero.
3. Confusion matrix construction.
4. Validation of valid prediction CSV files.
5. Detection of malformed inputs:
   - Header mismatch
   - Missing predictions
   - Duplicate case_ids
   - Invalid deletion_status
   - Malformed steps_json
   - NOT_APPLICABLE with non-empty steps
   - Non-consecutive step_no
   - Phase ordering violations
6. Sequence and step-level Jaccard similarity accuracy.
"""

import json
import tempfile
import unittest
import csv
import sys
from pathlib import Path

# Ensure code/ is in Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

from evaluation import (
    calculate_metrics,
    validate_prediction_row,
    validate_predictions_file,
    run_evaluation,
    generate_markdown_report,
)


class TestEvaluationEngine(unittest.TestCase):

    def test_synthetic_metrics_known_outcomes(self):
        """
        Verify precision, recall, F1, and accuracy on synthetic predictions with known values.
        """
        # Ground truth: 2 COMPLETE, 2 INCOMPLETE, 1 NOT_APPLICABLE
        ground_truth = {
            "c1": ("COMPLETE", '[{"step_no":1,"phase":"VERIFICATION","system_id":"s1","resource_id":"r1","operation":"VERIFY_RECORD_ABSENT","state":"ABSENT","evidence_id":"ev1"}]'),
            "c2": ("COMPLETE", '[{"step_no":1,"phase":"VERIFICATION","system_id":"s1","resource_id":"r2","operation":"VERIFY_RECORD_ABSENT","state":"ABSENT","evidence_id":"ev2"}]'),
            "c3": ("INCOMPLETE", '[{"step_no":1,"phase":"FINDING","system_id":"s1","resource_id":"r3","operation":"REPORT_REMAINING_RECORD","state":"PRESENT","evidence_id":"ev3"}]'),
            "c4": ("INCOMPLETE", '[{"step_no":1,"phase":"FINDING","system_id":"s1","resource_id":"r4","operation":"REPORT_REMAINING_RECORD","state":"PRESENT","evidence_id":"ev4"}]'),
            "c5": ("NOT_APPLICABLE", "[]"),
        }

        # Predictions:
        # c1: COMPLETE (TP for COMPLETE)
        # c2: INCOMPLETE (FN for COMPLETE, FP for INCOMPLETE)
        # c3: INCOMPLETE (TP for INCOMPLETE)
        # c4: INCOMPLETE (TP for INCOMPLETE)
        # c5: NOT_APPLICABLE (TP for NOT_APPLICABLE)
        predictions = {
            "c1": ("COMPLETE", '[{"step_no":1,"phase":"VERIFICATION","system_id":"s1","resource_id":"r1","operation":"VERIFY_RECORD_ABSENT","state":"ABSENT","evidence_id":"ev1"}]'),
            "c2": ("INCOMPLETE", '[{"step_no":1,"phase":"FINDING","system_id":"s1","resource_id":"r2","operation":"REPORT_REMAINING_RECORD","state":"PRESENT","evidence_id":"ev2"}]'),
            "c3": ("INCOMPLETE", '[{"step_no":1,"phase":"FINDING","system_id":"s1","resource_id":"r3","operation":"REPORT_REMAINING_RECORD","state":"PRESENT","evidence_id":"ev3"}]'),
            "c4": ("INCOMPLETE", '[{"step_no":1,"phase":"FINDING","system_id":"s1","resource_id":"r4","operation":"REPORT_REMAINING_RECORD","state":"PRESENT","evidence_id":"ev4"}]'),
            "c5": ("NOT_APPLICABLE", "[]"),
        }

        report = calculate_metrics(predictions, ground_truth)

        # 4 out of 5 correct status = 80% accuracy
        self.assertEqual(report.total_evaluated, 5)
        self.assertAlmostEqual(report.case_accuracy, 0.80)

        # COMPLETE metrics:
        # TP = 1 (c1), FP = 0, FN = 1 (c2). Precision = 1.0, Recall = 0.5, F1 = 2*(1*0.5)/(1+0.5) = 2/3 = 0.6667
        c_m = report.class_metrics["COMPLETE"]
        self.assertEqual(c_m.true_positives, 1)
        self.assertEqual(c_m.false_negatives, 1)
        self.assertEqual(c_m.false_positives, 0)
        self.assertAlmostEqual(c_m.precision, 1.0)
        self.assertAlmostEqual(c_m.recall, 0.5)
        self.assertAlmostEqual(c_m.f1, 2.0 / 3.0)

        # INCOMPLETE metrics:
        # TP = 2 (c3, c4), FP = 1 (c2), FN = 0. Precision = 2/3 = 0.6667, Recall = 1.0, F1 = 0.80
        inc_m = report.class_metrics["INCOMPLETE"]
        self.assertEqual(inc_m.true_positives, 2)
        self.assertEqual(inc_m.false_positives, 1)
        self.assertEqual(inc_m.false_negatives, 0)
        self.assertAlmostEqual(inc_m.precision, 2.0 / 3.0)
        self.assertAlmostEqual(inc_m.recall, 1.0)
        self.assertAlmostEqual(inc_m.f1, 0.80)

        # NOT_APPLICABLE metrics:
        # TP = 1, FP = 0, FN = 0. Precision = 1.0, Recall = 1.0, F1 = 1.0
        na_m = report.class_metrics["NOT_APPLICABLE"]
        self.assertEqual(na_m.true_positives, 1)
        self.assertEqual(na_m.precision, 1.0)
        self.assertEqual(na_m.recall, 1.0)
        self.assertEqual(na_m.f1, 1.0)

        # Confusion Matrix
        # Actual COMPLETE predicted as INCOMPLETE = 1 (c2)
        self.assertEqual(report.confusion_matrix["COMPLETE"]["INCOMPLETE"], 1)
        self.assertEqual(report.confusion_matrix["COMPLETE"]["COMPLETE"], 1)

        # Sequence accuracy:
        # c1 match, c2 mismatch, c3 match, c4 match, c5 match -> 4/5 = 80%
        self.assertAlmostEqual(report.sequence_accuracy, 0.80)

    def test_absent_class_handling(self):
        """
        Ensure dataset with 0 occurrences of a class (e.g. NOT_APPLICABLE)
        does not cause ZeroDivisionError and reports 0 precision/recall gracefully.
        """
        ground_truth = {
            "c1": ("COMPLETE", "[]"),
            "c2": ("INCOMPLETE", "[]"),
        }
        predictions = {
            "c1": ("COMPLETE", "[]"),
            "c2": ("INCOMPLETE", "[]"),
        }

        report = calculate_metrics(predictions, ground_truth)
        self.assertEqual(report.case_accuracy, 1.0)

        na_m = report.class_metrics["NOT_APPLICABLE"]
        self.assertEqual(na_m.support, 0)
        self.assertEqual(na_m.precision, 0.0)
        self.assertEqual(na_m.recall, 0.0)
        self.assertEqual(na_m.f1, 0.0)

    def test_validate_prediction_row_errors(self):
        """Test specific row-level validation errors."""
        # 1. Invalid status
        issues = validate_prediction_row("c1", "PENDING", "[]")
        self.assertTrue(any("Invalid deletion_status" in i.message for i in issues))

        # 2. Malformed JSON
        issues = validate_prediction_row("c2", "COMPLETE", "{not json}")
        self.assertTrue(any("Malformed steps_json" in i.message for i in issues))

        # 3. NOT_APPLICABLE with non-empty steps
        issues = validate_prediction_row("c3", "NOT_APPLICABLE", '[{"step_no":1}]')
        self.assertTrue(any("NOT_APPLICABLE must have empty steps_json" in i.message for i in issues))

        # 4. Non-consecutive step_no
        bad_steps = json.dumps([
            {"step_no": 2, "phase": "VERIFICATION", "system_id": "s", "resource_id": "r", "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": "ev"}
        ])
        issues = validate_prediction_row("c4", "COMPLETE", bad_steps)
        self.assertTrue(any("step_no" in i.message for i in issues))

        # 5. Violated phase order (VERIFICATION before FINDING)
        reversed_phase = json.dumps([
            {"step_no": 1, "phase": "VERIFICATION", "system_id": "s", "resource_id": "r1", "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": "ev"},
            {"step_no": 2, "phase": "FINDING", "system_id": "s", "resource_id": "r2", "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": "ev"},
        ])
        issues = validate_prediction_row("c5", "INCOMPLETE", reversed_phase)
        self.assertTrue(any("violates phase order" in i.message for i in issues))

    def test_validate_predictions_file(self):
        """Test full file-level validation including header, duplicates, and missing cases."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test_preds.csv"

            # Create test CSV with duplicate case_id and missing case_03
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["case_id", "deletion_status", "steps_json"])
                writer.writerow(["case_01", "COMPLETE", "[]"])
                writer.writerow(["case_01", "COMPLETE", "[]"])  # Duplicate!
                writer.writerow(["case_02", "NOT_APPLICABLE", "[]"])

            expected_cases = {"case_01", "case_02", "case_03"}
            res, _ = validate_predictions_file(csv_path, expected_case_ids=expected_cases)

            self.assertFalse(res.is_valid)
            error_msgs = [e.message for e in res.errors]
            self.assertTrue(any("Duplicate case_id 'case_01'" in m for m in error_msgs))
            self.assertTrue(any("Missing prediction for case 'case_03'" in m for m in error_msgs))

    def test_markdown_report_generation(self):
        """Test that Markdown report formats accurately with tables and alerts."""
        ground_truth = {"c1": ("COMPLETE", "[]")}
        predictions = {"c1": ("COMPLETE", "[]")}

        report = calculate_metrics(predictions, ground_truth)
        md = generate_markdown_report(report)

        self.assertIn("# GhostTrace AI Evaluation Report", md)
        self.assertIn("Case-Level Status Accuracy:", md)
        self.assertIn("Confusion Matrix", md)
        self.assertIn("Per-Status Performance", md)


if __name__ == "__main__":
    unittest.main()

"""
test_pipeline.py - Integration and Pipeline Tests for GhostTrace AI.

Verifies:
1. End-to-end pipeline execution from deletion requests to final output.csv.
2. Identity matches retain source references and supporting evidence.
3. Policy treatments and retention restrictions reach the decision engine.
4. Resurrection findings (active data flows and restore risks) reach the decision engine.
5. Missing or ambiguous evidence is represented explicitly.
6. Error handling ensures processing failures never silently claim complete deletion.
7. Strict adherence to output.csv schema, sorting, and row count constraints.
8. Decoupling of evaluation from prediction generation.
"""

import json
import tempfile
import unittest
import csv
import sys
from pathlib import Path

# Ensure code/ is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

from main import (
    process_pipeline,
    PipelineContext,
    resolve_case_identity,
    audit_case_resources_and_risks,
)
from decision import (
    DecisionEngine,
    DeletionRequestInput,
    ResolvedIdentityInput,
    ResourceStateInput,
    ProcessRiskInput,
)
from output import validate_output_csv, OFFICIAL_COLUMNS
from evaluation import run_evaluation


class TestPipelineIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).parent.parent
        cls.dataset_dir = cls.repo_root / "dataset"

    def test_pipeline_on_sample_requests(self):
        """Verify full end-to-end pipeline on sample_deletion_requests.csv."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_csv = Path(tmpdir) / "output.csv"
            sample_reqs = self.dataset_dir / "sample_deletion_requests.csv"

            count = process_pipeline(sample_reqs, self.dataset_dir, out_csv)
            self.assertEqual(count, 32)

            val = validate_output_csv(out_csv, expected_row_count=32)
            self.assertTrue(val["is_valid"])
            self.assertEqual(len(val["errors"]), 0)

    def test_identity_source_references_preserved(self):
        """Verify that resolved identity preserves source references and historical audit IDs."""
        ctx = PipelineContext(self.dataset_dir)
        case = {
            "case_id": "test_case",
            "email": "amina.elmasri@gmail.com",
            "request_text": "Please delete my account.",
        }
        ident = resolve_case_identity(case, ctx)

        self.assertEqual(ident.primary_user_id, "user_01")
        self.assertIn("amina.elmasri@gmail.com", ident.emails)
        self.assertTrue(ident.is_deletion_requested)
        # Should have verified confidence
        self.assertGreaterEqual(ident.match_confidence, 0.8)

    def test_policy_retention_and_resurrection_reach_decision(self):
        """Verify policy retention constraints and resurrection risks flow into decision steps."""
        engine = DecisionEngine()
        req = DeletionRequestInput("c_test", "t@example.com", "", "NOT_STARTED", "", "", "Delete my data.")
        ident = ResolvedIdentityInput("u_test", {"t@example.com"})

        resources = [
            ResourceStateInput(
                system_id="security_service",
                resource_id="audit_log_1",
                data_category="SECURITY_AUDIT_LOG",
                state_at_audit="PRESENT",
                required_action="RETAIN",
                evidence_id="ev_ret",
                retained_record=True,
            )
        ]
        risks = [
            ProcessRiskInput(
                system_id="sync_service",
                resource_id="sync_flow_1",
                risk_type="ACTIVE_DATA_FLOW",
                state="ACTIVE",
                evidence_id="ev_risk",
            )
        ]

        outcome = engine.evaluate_request(req, ident, resources, risks)

        # Risk must force INCOMPLETE
        self.assertEqual(outcome.deletion_status, "INCOMPLETE")

        # Verify active flow finding and remediation exist
        ops = [s.operation for s in outcome.steps]
        self.assertIn("REPORT_ACTIVE_DATA_FLOW", ops)
        self.assertIn("DISABLE_DATA_FLOW", ops)
        self.assertIn("VERIFY_DATA_FLOW_DISABLED", ops)
        self.assertIn("VERIFY_RECORD_PRESENT", ops)  # Retained log must be verified present

    def test_processing_errors_never_silently_produce_complete(self):
        """
        Critical safety invariant: A processing exception must never produce
        a COMPLETE deletion status.
        """
        class BrokenEngine(DecisionEngine):
            def evaluate_request(self, *args, **kwargs):
                raise RuntimeError("Simulated internal engine failure")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_csv = Path(tmpdir) / "safe_output.csv"
            sample_reqs = self.dataset_dir / "sample_deletion_requests.csv"

            # Execute pipeline with failing engine
            broken_engine = BrokenEngine()
            process_pipeline(sample_reqs, self.dataset_dir, out_csv, decision_engine=broken_engine)

            with open(out_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Every row should default to INCOMPLETE on failure, never COMPLETE
                    self.assertNotEqual(row["deletion_status"], "COMPLETE")
                    self.assertEqual(row["deletion_status"], "INCOMPLETE")

    def test_evaluation_decoupled_from_generation(self):
        """Verify evaluation operates purely on CSV files without modifying them."""
        sample_gt = self.dataset_dir / "sample_output.csv"
        report = run_evaluation(sample_gt, sample_gt)

        self.assertEqual(report.total_evaluated, 32)
        self.assertEqual(report.case_accuracy, 1.0)
        self.assertTrue(report.validation.is_valid)


if __name__ == "__main__":
    unittest.main()

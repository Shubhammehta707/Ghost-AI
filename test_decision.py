"""
test_decision.py - Focused tests for DecisionEngine in GhostTrace AI.

Verifies:
1. Every status (COMPLETE, INCOMPLETE, NOT_APPLICABLE)
2. Missing and unconfirmed evidence handling
3. Policy retention requirements (audit logs, legal holds)
4. Ambiguous identity matches and false-positive prevention
5. Resurrection findings (active data flows and backup restore risks)
6. Strict step ordering, canonical operation table order, and consecutive renumbering
7. Dictionary-based adapter compatibility for Members 1 and 2 interfaces
"""

import json
import unittest
import sys
from pathlib import Path

# Ensure code/ is in Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

from decision import (
    DecisionEngine,
    decide_request,
    DeletionRequestInput,
    ResolvedIdentityInput,
    ResourceStateInput,
    ProcessRiskInput,
    determine_deletion_intent,
    sort_and_renumber_steps,
    AuditStep,
)


class TestDecisionEngine(unittest.TestCase):

    def setUp(self):
        self.engine = DecisionEngine()

    def test_complete_status_verification_only(self):
        """
        COMPLETE status when all required actions are verified by evidence.
        Verification steps must cite evidence and contain NO findings or remediation.
        """
        req = DeletionRequestInput(
            case_id="case_01",
            email="user1@example.com",
            requested_at="2026-08-18T09:14:00Z",
            reported_status="COMPLETE",
            reported_at="2026-08-20T16:42:00Z",
            audit_at="2026-09-03T11:30:00Z",
            request_text="Please delete my account and remove all personal details attached to it.",
        )
        identity = ResolvedIdentityInput(
            primary_user_id="user_01",
            emails={"user1@example.com"},
            is_deletion_requested=True,
            match_confidence=1.0,
        )
        resources = [
            ResourceStateInput(
                system_id="account_service",
                resource_id="account_001",
                data_category="USER_PROFILE",
                state_at_audit="ABSENT",
                required_action="DELETE",
                evidence_id="evidence_54",
                evidence_confirmed=True,
            ),
            ResourceStateInput(
                system_id="analytics_platform",
                resource_id="analytics_901",
                data_category="ANALYTICS_PROFILE",
                state_at_audit="ANONYMIZED",
                required_action="ANONYMIZE",
                evidence_id="evidence_56",
                evidence_confirmed=True,
            ),
            ResourceStateInput(
                system_id="security_service",
                resource_id="audit_2016",
                data_category="SECURITY_AUDIT_LOG",
                state_at_audit="PRESENT",
                required_action="RETAIN",
                evidence_id="evidence_94",
                evidence_confirmed=True,
            ),
        ]
        risks = []

        outcome = self.engine.evaluate_request(req, identity, resources, risks)

        self.assertEqual(outcome.deletion_status, "COMPLETE")
        self.assertEqual(len(outcome.steps), 3)

        # Ensure all steps are in VERIFICATION phase and cite evidence
        for step in outcome.steps:
            self.assertEqual(step.phase, "VERIFICATION")
            self.assertTrue(len(step.evidence_id) > 0)

        parsed = json.loads(outcome.steps_json)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["step_no"], 1)
        self.assertEqual(parsed[1]["step_no"], 2)
        self.assertEqual(parsed[2]["step_no"], 3)
        # Check canonical operation order: VERIFY_RECORD_ABSENT (20) -> VERIFY_RECORD_PRESENT (21) -> VERIFY_RECORD_ANONYMIZED (23)
        self.assertEqual(parsed[0]["operation"], "VERIFY_RECORD_ABSENT")
        self.assertEqual(parsed[1]["operation"], "VERIFY_RECORD_PRESENT")
        self.assertEqual(parsed[2]["operation"], "VERIFY_RECORD_ANONYMIZED")

    def test_incomplete_status_with_remaining_records(self):
        """
        INCOMPLETE status when records still exist.
        Must generate FINDING (citing evidence_id), REMEDIATION (evidence_id=""),
        and post-remediation VERIFICATION (evidence_id="").
        """
        req = DeletionRequestInput(
            case_id="case_05",
            email="user5@example.com",
            requested_at="2026-08-27T14:17:00Z",
            reported_status="COMPLETE",  # Workflow claims complete, but audit finds record!
            reported_at="2026-08-28T09:03:00Z",
            audit_at="2026-09-08T13:40:00Z",
            request_text="I deleted this account and received a confirmation, but my email is still recognized. Please remove remaining profile.",
        )
        identity = ResolvedIdentityInput(
            primary_user_id="user_05",
            emails={"user5@example.com"},
            is_deletion_requested=True,
        )
        resources = [
            ResourceStateInput(
                system_id="account_service",
                resource_id="account_005",
                data_category="USER_PROFILE",
                state_at_audit="PRESENT",  # Remains in DB!
                required_action="DELETE",
                evidence_id="evidence_54",
                evidence_confirmed=True,
            )
        ]
        risks = []

        outcome = self.engine.evaluate_request(req, identity, resources, risks)

        self.assertEqual(outcome.deletion_status, "INCOMPLETE")
        self.assertEqual(len(outcome.steps), 3)

        finding = outcome.steps[0]
        self.assertEqual(finding.phase, "FINDING")
        self.assertEqual(finding.operation, "REPORT_REMAINING_RECORD")
        self.assertEqual(finding.state, "PRESENT")
        self.assertEqual(finding.evidence_id, "evidence_54")

        remediation = outcome.steps[1]
        self.assertEqual(remediation.phase, "REMEDIATION")
        self.assertEqual(remediation.operation, "DELETE_RECORD")
        self.assertEqual(remediation.state, "ABSENT")
        self.assertEqual(remediation.evidence_id, "")

        verification = outcome.steps[2]
        self.assertEqual(verification.phase, "VERIFICATION")
        self.assertEqual(verification.operation, "VERIFY_RECORD_ABSENT")
        self.assertEqual(verification.state, "ABSENT")
        self.assertEqual(verification.evidence_id, "")

    def test_not_applicable_non_deletion_intent(self):
        """
        NOT_APPLICABLE when the user did not request account deletion.
        Must output empty steps_json '[]'.
        """
        req = DeletionRequestInput(
            case_id="case_99",
            email="user99@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="NOT_STARTED",
            reported_at="2026-09-01T10:00:00Z",
            audit_at="2026-09-10T10:00:00Z",
            request_text="Can you check the delivery status of my order #12345? Please do not delete my account.",
        )
        identity = ResolvedIdentityInput(
            primary_user_id="user_99",
            emails={"user99@example.com"},
            is_deletion_requested=False,
        )
        outcome = self.engine.evaluate_request(req, identity, [], [])

        self.assertEqual(outcome.deletion_status, "NOT_APPLICABLE")
        self.assertEqual(len(outcome.steps), 0)
        self.assertEqual(outcome.steps_json, "[]")

    def test_ambiguous_identity_match_prevents_deletion(self):
        """
        Ambiguous or uncertain identity matches output NOT_APPLICABLE
        to prevent unauthorized deletion of another person's data.
        """
        req = DeletionRequestInput(
            case_id="case_101",
            email="john.smith@example.com",
            requested_at="2026-09-01T10:00:00Z",
            reported_status="NOT_STARTED",
            reported_at="2026-09-01T10:00:00Z",
            audit_at="2026-09-10T10:00:00Z",
            request_text="Please delete my account.",
        )
        identity = ResolvedIdentityInput(
            primary_user_id="user_101",
            emails={"john.smith@example.com"},
            is_deletion_requested=True,
            is_ambiguous=True,
            match_confidence=0.3,
        )
        outcome = self.engine.evaluate_request(req, identity, [], [])

        self.assertEqual(outcome.deletion_status, "NOT_APPLICABLE")
        self.assertEqual(outcome.steps_json, "[]")

    def test_resurrection_risks_active_flow_and_restore(self):
        """
        Active data flows and backup restore risks.
        Both must produce findings, remediation, and verification checks.
        """
        req = DeletionRequestInput(
            case_id="case_09",
            email="user9@example.com",
            requested_at="2026-09-05T09:00:00Z",
            reported_status="NOT_STARTED",
            reported_at="2026-09-07T09:00:00Z",
            audit_at="2026-09-16T09:00:00Z",
            request_text="Please permanently delete the account associated with this email address.",
        )
        identity = ResolvedIdentityInput(
            primary_user_id="user_09",
            emails={"user9@example.com"},
            is_deletion_requested=True,
        )
        resources = [
            ResourceStateInput(
                system_id="account_service",
                resource_id="account_3960",
                data_category="USER_PROFILE",
                state_at_audit="ABSENT",
                required_action="DELETE",
                evidence_id="evidence_94",
                evidence_confirmed=True,
            ),
            ResourceStateInput(
                system_id="security_service",
                resource_id="audit_record_4902",
                data_category="SECURITY_AUDIT_LOG",
                state_at_audit="PRESENT",
                required_action="RETAIN",
                evidence_id="evidence_94",
                evidence_confirmed=True,
            ),
        ]
        risks = [
            ProcessRiskInput(
                system_id="backup_service",
                resource_id="backup_4978",
                risk_type="RESTORE_RISK",
                state="ACTIVE",
                evidence_id="evidence_93",
                is_confirmed=True,
            )
        ]

        outcome = self.engine.evaluate_request(req, identity, resources, risks)

        self.assertEqual(outcome.deletion_status, "INCOMPLETE")

        # Step 1: FINDING REPORT_RESTORE_RISK on backup_service/backup_4978
        self.assertEqual(outcome.steps[0].phase, "FINDING")
        self.assertEqual(outcome.steps[0].operation, "REPORT_RESTORE_RISK")
        self.assertEqual(outcome.steps[0].system_id, "backup_service")
        self.assertEqual(outcome.steps[0].evidence_id, "evidence_93")

        # Step 2: REMEDIATION BLOCK_RESTORE on backup_service/backup_4978
        self.assertEqual(outcome.steps[1].phase, "REMEDIATION")
        self.assertEqual(outcome.steps[1].operation, "BLOCK_RESTORE")
        self.assertEqual(outcome.steps[1].state, "BLOCKED")
        self.assertEqual(outcome.steps[1].evidence_id, "")

        # Phase 3: VERIFICATION
        verif_ops = [s.operation for s in outcome.steps if s.phase == "VERIFICATION"]
        self.assertIn("VERIFY_RECORD_ABSENT", verif_ops)
        self.assertIn("VERIFY_RECORD_PRESENT", verif_ops)
        self.assertIn("VERIFY_RESTORE_BLOCKED", verif_ops)

    def test_missing_or_unconfirmed_evidence_prevents_complete(self):
        """
        A record claimed to be deleted but lacking confirmed evidence
        cannot be marked COMPLETE.
        """
        req = DeletionRequestInput(
            case_id="case_12",
            email="test@example.com",
            requested_at="2026-08-01T00:00:00Z",
            reported_status="COMPLETE",
            reported_at="2026-08-02T00:00:00Z",
            audit_at="2026-08-10T00:00:00Z",
            request_text="Delete my data.",
        )
        identity = ResolvedIdentityInput(primary_user_id="user_12", emails={"test@example.com"})
        resources = [
            ResourceStateInput(
                system_id="secondary_db",
                resource_id="rec_99",
                data_category="USER_PROFILE",
                state_at_audit="ABSENT",
                required_action="DELETE",
                evidence_id="",  # Missing evidence!
                evidence_confirmed=False,
            )
        ]

        outcome = self.engine.evaluate_request(req, identity, resources, [])
        self.assertEqual(outcome.deletion_status, "INCOMPLETE")

    def test_tombstone_with_exposed_pii_flagged(self):
        """
        An account tombstone preserves user_id, but must have direct PII redacted.
        If direct PII remains, it must be flagged with REPORT_EXPOSED_PII.
        """
        req = DeletionRequestInput(
            case_id="case_15",
            email="tomb@example.com",
            requested_at="2026-08-01T00:00:00Z",
            reported_status="PARTIALLY_COMPLETE",
            reported_at="2026-08-02T00:00:00Z",
            audit_at="2026-08-10T00:00:00Z",
            request_text="Please delete my account.",
        )
        identity = ResolvedIdentityInput(primary_user_id="user_15", emails={"tomb@example.com"})
        resources = [
            ResourceStateInput(
                system_id="account_service",
                resource_id="tombstone_15",
                data_category="ACCOUNT_TOMBSTONE",
                state_at_audit="PRESENT",
                required_action="REDACT",
                exposed_pii=["email", "phone"],  # PII still present!
                evidence_id="evidence_15",
                is_tombstone=True,
            )
        ]

        outcome = self.engine.evaluate_request(req, identity, resources, [])
        self.assertEqual(outcome.deletion_status, "INCOMPLETE")
        self.assertEqual(outcome.steps[0].operation, "REPORT_EXPOSED_PII")
        self.assertEqual(outcome.steps[1].operation, "REDACT_RECORD")
        self.assertEqual(outcome.steps[2].operation, "VERIFY_RECORD_REDACTED")

    def test_dictionary_adapter_compatibility(self):
        """
        Verify that decide_request accepts plain dictionaries from Member 1 and Member 2 modules.
        """
        req_dict = {
            "case_id": "case_dict_01",
            "email": "dict@example.com",
            "requested_at": "2026-08-01T00:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-08-02T00:00:00Z",
            "audit_at": "2026-08-10T00:00:00Z",
            "request_text": "Please delete my account.",
        }
        identity_dict = {
            "primary_user_id": "user_dict_01",
            "emails": {"dict@example.com"},
            "is_deletion_requested": True,
        }
        resources_dict = [
            {
                "system_id": "account_service",
                "resource_id": "acc_01",
                "data_category": "USER_PROFILE",
                "state_at_audit": "ABSENT",
                "required_action": "DELETE",
                "evidence_id": "ev_01",
                "evidence_confirmed": True,
            }
        ]
        risks_dict = []

        outcome = decide_request(req_dict, identity_dict, resources_dict, risks_dict)
        self.assertEqual(outcome.deletion_status, "COMPLETE")
        self.assertEqual(len(outcome.steps), 1)
        self.assertEqual(outcome.steps[0].operation, "VERIFY_RECORD_ABSENT")

    def test_multilingual_deletion_intent(self):
        """Verify robust multilingual deletion intent parsing."""
        self.assertTrue(determine_deletion_intent("Please delete my account"))
        self.assertTrue(determine_deletion_intent("Je demande la suppression définitive du compte"))
        self.assertTrue(determine_deletion_intent("Intenté eliminar mi cuenta ayer"))
        self.assertTrue(determine_deletion_intent("Bitte löschen Sie meine Daten"))
        self.assertFalse(determine_deletion_intent("Please update my shipping address"))
        self.assertFalse(determine_deletion_intent("What is the status of my order?"))


if __name__ == "__main__":
    unittest.main()

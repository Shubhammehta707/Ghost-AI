"""
decision.py - Decision Engine for GhostTrace AI (Member 3)

This module implements the core decision logic for evaluating deletion requests:
- Evaluates individual deletion requests against resolved identities, resource states,
  policy rules, and dependency risks.
- Enforces official problem statement definitions for COMPLETE, INCOMPLETE, and NOT_APPLICABLE.
- Produces correctly ordered findings, remediation plans, and verification steps.
- Formats steps_json strictly adhering to the benchmark schema and sorting requirements.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Any, Union
import json
import re


# ---------------------------------------------------------------------------
# Canonical Phase and Operation Enums / Order Constants
# ---------------------------------------------------------------------------

PHASE_ORDER = {
    "FINDING": 1,
    "REMEDIATION": 2,
    "VERIFICATION": 3,
}

OPERATION_ORDER = {
    # Phase: FINDING
    "REPORT_REMAINING_RECORD": 1,
    "REPORT_EXPOSED_PII": 2,
    "REPORT_ACTIVE_DATA_FLOW": 3,
    "REPORT_RESTORE_RISK": 4,
    # Phase: REMEDIATION
    "DISABLE_DATA_FLOW": 10,
    "BLOCK_RESTORE": 11,
    "DELETE_RECORD": 12,
    "REDACT_RECORD": 13,
    "ANONYMIZE_RECORD": 14,
    # Phase: VERIFICATION
    "VERIFY_RECORD_ABSENT": 20,
    "VERIFY_RECORD_PRESENT": 21,
    "VERIFY_RECORD_REDACTED": 22,
    "VERIFY_RECORD_ANONYMIZED": 23,
    "VERIFY_DATA_FLOW_DISABLED": 24,
    "VERIFY_RESTORE_BLOCKED": 25,
}

VALID_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}


# ---------------------------------------------------------------------------
# Domain Data Classes
# ---------------------------------------------------------------------------

@dataclass
class AuditStep:
    """Represents a single finding, remediation action, or verification check."""
    step_no: int
    phase: str
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_no": self.step_no,
            "phase": self.phase,
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation,
            "state": self.state,
            "evidence_id": self.evidence_id,
        }


@dataclass
class DeletionRequestInput:
    """Input deletion request record from deletion_requests.csv."""
    case_id: str
    email: str
    requested_at: str
    reported_status: str
    reported_at: str
    audit_at: str
    request_text: str


@dataclass
class ResolvedIdentityInput:
    """Resolved identity from Member 1 (identity.py)."""
    primary_user_id: Optional[str] = None
    emails: Set[str] = field(default_factory=set)
    names: Set[str] = field(default_factory=set)
    phones: Set[str] = field(default_factory=set)
    email_hashes: Set[str] = field(default_factory=set)
    is_deletion_requested: bool = True
    is_ambiguous: bool = False
    match_confidence: float = 1.0
    linked_audit_ids: List[str] = field(default_factory=list)


@dataclass
class ResourceStateInput:
    """Discovered resource state and policy requirements from Member 2 (policy.py)."""
    system_id: str
    resource_id: str
    data_category: str
    state_at_audit: str  # 'ABSENT', 'PRESENT', 'REDACTED', 'ANONYMIZED'
    required_action: str  # 'DELETE', 'REDACT', 'ANONYMIZE', 'RETAIN'
    exposed_pii: List[str] = field(default_factory=list)
    evidence_id: str = ""
    evidence_confirmed: bool = True
    is_tombstone: bool = False
    retained_record: bool = False


@dataclass
class ProcessRiskInput:
    """Active process, replication, or restore risk from Member 2 (dependencies.py)."""
    system_id: str
    resource_id: str
    risk_type: str  # 'ACTIVE_DATA_FLOW' or 'RESTORE_RISK'
    state: str = "ACTIVE"
    evidence_id: str = ""
    is_confirmed: bool = True


@dataclass
class DecisionOutcome:
    """Final decision output for a single case."""
    case_id: str
    deletion_status: str
    steps: List[AuditStep]
    steps_json: str
    rationale: str = ""


# ---------------------------------------------------------------------------
# Intent Detection Helper
# ---------------------------------------------------------------------------

NON_DELETION_PATTERNS = [
    r"\b(do not delete|don't delete|keep my account|cancel (my )?deletion|cancel request)\b",
    r"\b(update my (email|address|phone|profile)|change my (email|password))\b",
    r"\b(what data do you have|download my data|access my data|data export)\b",
    r"\b(status of my order|track my order|delivery issue|refund status)\b",
]

DELETION_PATTERNS = [
    r"\b(delete|deletion|deleting|deleted|remove|removal|removing|removed|erase|erasure|close|closing|closed)\b",
    r"\b(eliminar|eliminaci[oó]n|borrar|borrado|suprimir|supresi[oó]n|effacer|effacement|supprimer|suppression)\b",
    r"\b(l[oö]schen|l[oö]schung|entfernen|entfernung|cancellare|cancellazione|apagar|apaga[cç][aã]o)\b",
    r"\b(definitiv[a-z]*|permanently|forever|entirely)\b",
]


def determine_deletion_intent(request_text: str) -> bool:
    """
    Determines whether the request text actually requests personal data / account deletion.
    Handles multilingual phrasing (English, French, Spanish, German).
    """
    if not request_text or not request_text.strip():
        return False

    text_lower = request_text.lower().strip()

    # Check for explicit non-deletion / cancellation phrases
    for pattern in NON_DELETION_PATTERNS:
        if re.search(pattern, text_lower):
            return False

    # Check for positive deletion phrases
    for pattern in DELETION_PATTERNS:
        if re.search(pattern, text_lower):
            return True

    return False


# ---------------------------------------------------------------------------
# Step Sorting & Normalization
# ---------------------------------------------------------------------------

def sort_and_renumber_steps(steps: List[AuditStep]) -> List[AuditStep]:
    """
    Orders steps strictly per the problem statement specification:
    1. Phase: FINDING -> REMEDIATION -> VERIFICATION
    2. Operation: Canonically ordered by the problem statement operation table
    3. System ID: Ascending alphabetically
    4. Resource ID: Ascending alphabetically
    5. Consecutive step_no starting at 1
    """
    def sort_key(s: AuditStep):
        p_val = PHASE_ORDER.get(s.phase, 99)
        op_val = OPERATION_ORDER.get(s.operation, 99)
        return (p_val, op_val, s.system_id, s.resource_id)

    sorted_steps = sorted(steps, key=sort_key)
    renumbered = []
    for idx, s in enumerate(sorted_steps, start=1):
        renumbered.append(AuditStep(
            step_no=idx,
            phase=s.phase,
            system_id=s.system_id,
            resource_id=s.resource_id,
            operation=s.operation,
            state=s.state,
            evidence_id=s.evidence_id,
        ))
    return renumbered


def serialize_steps(steps: List[AuditStep]) -> str:
    """Serializes the ordered list of AuditStep objects to a compact JSON string."""
    if not steps:
        return "[]"
    raw_dicts = [s.to_dict() for s in steps]
    return json.dumps(raw_dicts, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Core Decision Engine
# ---------------------------------------------------------------------------

class DecisionEngine:
    """
    Deterministic decision engine enforcing official completion criteria
    and formatting constraints for GhostTrace AI.
    """

    def evaluate_request(
        self,
        request: Union[DeletionRequestInput, Dict[str, Any]],
        identity: Union[ResolvedIdentityInput, Dict[str, Any]],
        resources: List[Union[ResourceStateInput, Dict[str, Any]]],
        risks: List[Union[ProcessRiskInput, Dict[str, Any]]],
    ) -> DecisionOutcome:
        """
        Evaluates a single case and returns a DecisionOutcome.
        Accepts either dataclass instances or raw dictionaries for flexible interoperability.
        """
        # Normalize request input
        case_id = request.case_id if isinstance(request, DeletionRequestInput) else str(request.get("case_id", ""))
        request_text = request.request_text if isinstance(request, DeletionRequestInput) else str(request.get("request_text", ""))

        # Normalize identity input
        if isinstance(identity, ResolvedIdentityInput):
            is_deletion_req = identity.is_deletion_requested
            is_ambiguous = identity.is_ambiguous
            match_confidence = identity.match_confidence
        else:
            is_deletion_req = bool(identity.get("is_deletion_requested", True))
            is_ambiguous = bool(identity.get("is_ambiguous", False))
            match_confidence = float(identity.get("match_confidence", 1.0))

        # 1. Check Deletion Intent
        # If identity parser flagged it as False, or text indicates no deletion intent:
        if not is_deletion_req or not determine_deletion_intent(request_text):
            return DecisionOutcome(
                case_id=case_id,
                deletion_status="NOT_APPLICABLE",
                steps=[],
                steps_json="[]",
                rationale="The person did not request deletion. No deletion actions authorized."
            )

        # If identity resolution is ambiguous or uncertain, cannot execute authorized deletion
        if is_ambiguous or match_confidence < 0.5:
            return DecisionOutcome(
                case_id=case_id,
                deletion_status="NOT_APPLICABLE",
                steps=[],
                steps_json="[]",
                rationale="Identity match is uncertain or ambiguous; preventing unauthorized deletion."
            )

        # 2. Normalize resource items
        norm_resources: List[ResourceStateInput] = []
        for r in resources:
            if isinstance(r, ResourceStateInput):
                norm_resources.append(r)
            else:
                norm_resources.append(ResourceStateInput(
                    system_id=str(r.get("system_id", "")),
                    resource_id=str(r.get("resource_id", "")),
                    data_category=str(r.get("data_category", "")),
                    state_at_audit=str(r.get("state_at_audit", "PRESENT")),
                    required_action=str(r.get("required_action", "DELETE")),
                    exposed_pii=list(r.get("exposed_pii", [])),
                    evidence_id=str(r.get("evidence_id", "")),
                    evidence_confirmed=bool(r.get("evidence_confirmed", True)),
                    is_tombstone=bool(r.get("is_tombstone", False)),
                    retained_record=bool(r.get("retained_record", False)),
                ))

        # 3. Normalize process risk items
        norm_risks: List[ProcessRiskInput] = []
        for risk in risks:
            if isinstance(risk, ProcessRiskInput):
                norm_risks.append(risk)
            else:
                norm_risks.append(ProcessRiskInput(
                    system_id=str(risk.get("system_id", "")),
                    resource_id=str(risk.get("resource_id", "")),
                    risk_type=str(risk.get("risk_type", "ACTIVE_DATA_FLOW")),
                    state=str(risk.get("state", "ACTIVE")),
                    evidence_id=str(risk.get("evidence_id", "")),
                    is_confirmed=bool(risk.get("is_confirmed", True)),
                ))

        # 4. Evaluate Findings, Remediation, and Verification steps
        finding_steps: List[AuditStep] = []
        remediation_steps: List[AuditStep] = []
        future_verification_steps: List[AuditStep] = []
        confirmed_verification_steps: List[AuditStep] = []

        is_incomplete = False

        # Evaluate Resource Compliance
        for r in norm_resources:
            req_action = r.required_action.upper()
            curr_state = r.state_at_audit.upper()
            has_exposed_pii = bool(r.exposed_pii)
            evidence_id = r.evidence_id if r.evidence_confirmed else ""

            if req_action == "DELETE":
                if curr_state == "ABSENT" and r.evidence_confirmed and r.evidence_id:
                    # Verified deleted
                    confirmed_verification_steps.append(AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="VERIFY_RECORD_ABSENT",
                        state="ABSENT",
                        evidence_id=r.evidence_id,
                    ))
                    future_verification_steps.append(AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="VERIFY_RECORD_ABSENT",
                        state="ABSENT",
                        evidence_id="",
                    ))
                else:
                    # Record still exists or lacks confirmed proof of deletion
                    is_incomplete = True
                    finding_steps.append(AuditStep(
                        step_no=0,
                        phase="FINDING",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="REPORT_REMAINING_RECORD",
                        state="PRESENT",
                        evidence_id=evidence_id,
                    ))
                    remediation_steps.append(AuditStep(
                        step_no=0,
                        phase="REMEDIATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="DELETE_RECORD",
                        state="ABSENT",
                        evidence_id="",
                    ))
                    future_verification_steps.append(AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="VERIFY_RECORD_ABSENT",
                        state="ABSENT",
                        evidence_id="",
                    ))

            elif req_action == "REDACT":
                if curr_state == "REDACTED" and not has_exposed_pii and r.evidence_confirmed and r.evidence_id:
                    # Verified redacted
                    confirmed_verification_steps.append(AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="VERIFY_RECORD_REDACTED",
                        state="REDACTED",
                        evidence_id=r.evidence_id,
                    ))
                    future_verification_steps.append(AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="VERIFY_RECORD_REDACTED",
                        state="REDACTED",
                        evidence_id="",
                    ))
                else:
                    # PII remains or record is still unredacted
                    is_incomplete = True
                    finding_steps.append(AuditStep(
                        step_no=0,
                        phase="FINDING",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="REPORT_EXPOSED_PII",
                        state="PRESENT",
                        evidence_id=evidence_id,
                    ))
                    remediation_steps.append(AuditStep(
                        step_no=0,
                        phase="REMEDIATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="REDACT_RECORD",
                        state="REDACTED",
                        evidence_id="",
                    ))
                    future_verification_steps.append(AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="VERIFY_RECORD_REDACTED",
                        state="REDACTED",
                        evidence_id="",
                    ))

            elif req_action == "ANONYMIZE":
                if curr_state == "ANONYMIZED" and not has_exposed_pii and r.evidence_confirmed and r.evidence_id:
                    # Verified anonymized
                    confirmed_verification_steps.append(AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="VERIFY_RECORD_ANONYMIZED",
                        state="ANONYMIZED",
                        evidence_id=r.evidence_id,
                    ))
                    future_verification_steps.append(AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="VERIFY_RECORD_ANONYMIZED",
                        state="ANONYMIZED",
                        evidence_id="",
                    ))
                else:
                    # Analytics / telemetry record still attributable
                    is_incomplete = True
                    finding_steps.append(AuditStep(
                        step_no=0,
                        phase="FINDING",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="REPORT_EXPOSED_PII",
                        state="PRESENT",
                        evidence_id=evidence_id,
                    ))
                    remediation_steps.append(AuditStep(
                        step_no=0,
                        phase="REMEDIATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="ANONYMIZE_RECORD",
                        state="ANONYMIZED",
                        evidence_id="",
                    ))
                    future_verification_steps.append(AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="VERIFY_RECORD_ANONYMIZED",
                        state="ANONYMIZED",
                        evidence_id="",
                    ))

            elif req_action == "RETAIN":
                # Retained records (e.g. security audit log, legal hold, backup archive)
                if curr_state == "PRESENT" and r.evidence_confirmed and r.evidence_id:
                    confirmed_verification_steps.append(AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="VERIFY_RECORD_PRESENT",
                        state="PRESENT",
                        evidence_id=r.evidence_id,
                    ))
                    future_verification_steps.append(AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="VERIFY_RECORD_PRESENT",
                        state="PRESENT",
                        evidence_id="",
                    ))
                else:
                    # Required retained record was improperly deleted or lost
                    is_incomplete = True
                    finding_steps.append(AuditStep(
                        step_no=0,
                        phase="FINDING",
                        system_id=r.system_id,
                        resource_id=r.resource_id,
                        operation="REPORT_REMAINING_RECORD",
                        state="PRESENT",
                        evidence_id=evidence_id,
                    ))

        # Evaluate Process and Restoration Risks
        for risk in norm_risks:
            risk_type = risk.risk_type.upper()
            evidence_id = risk.evidence_id if risk.is_confirmed else ""
            is_incomplete = True

            if risk_type == "ACTIVE_DATA_FLOW":
                finding_steps.append(AuditStep(
                    step_no=0,
                    phase="FINDING",
                    system_id=risk.system_id,
                    resource_id=risk.resource_id,
                    operation="REPORT_ACTIVE_DATA_FLOW",
                    state="ACTIVE",
                    evidence_id=evidence_id,
                ))
                remediation_steps.append(AuditStep(
                    step_no=0,
                    phase="REMEDIATION",
                    system_id=risk.system_id,
                    resource_id=risk.resource_id,
                    operation="DISABLE_DATA_FLOW",
                    state="DISABLED",
                    evidence_id="",
                ))
                future_verification_steps.append(AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=risk.system_id,
                    resource_id=risk.resource_id,
                    operation="VERIFY_DATA_FLOW_DISABLED",
                    state="DISABLED",
                    evidence_id="",
                ))

            elif risk_type == "RESTORE_RISK":
                finding_steps.append(AuditStep(
                    step_no=0,
                    phase="FINDING",
                    system_id=risk.system_id,
                    resource_id=risk.resource_id,
                    operation="REPORT_RESTORE_RISK",
                    state="ACTIVE",
                    evidence_id=evidence_id,
                ))
                remediation_steps.append(AuditStep(
                    step_no=0,
                    phase="REMEDIATION",
                    system_id=risk.system_id,
                    resource_id=risk.resource_id,
                    operation="BLOCK_RESTORE",
                    state="BLOCKED",
                    evidence_id="",
                ))
                future_verification_steps.append(AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=risk.system_id,
                    resource_id=risk.resource_id,
                    operation="VERIFY_RESTORE_BLOCKED",
                    state="BLOCKED",
                    evidence_id="",
                ))

        # 5. Assemble Decision Outcome
        if is_incomplete:
            all_steps = finding_steps + remediation_steps + future_verification_steps
            final_steps = sort_and_renumber_steps(all_steps)
            return DecisionOutcome(
                case_id=case_id,
                deletion_status="INCOMPLETE",
                steps=final_steps,
                steps_json=serialize_steps(final_steps),
                rationale="Unfulfilled policy treatments, exposed PII, or active recreation risks detected."
            )
        else:
            final_steps = sort_and_renumber_steps(confirmed_verification_steps)
            return DecisionOutcome(
                case_id=case_id,
                deletion_status="COMPLETE",
                steps=final_steps,
                steps_json=serialize_steps(final_steps),
                rationale="All copies treated per policy, no active flows/risks, and verified by evidence."
            )


# Module-level convenience function
def decide_request(
    request: Union[DeletionRequestInput, Dict[str, Any]],
    identity: Union[ResolvedIdentityInput, Dict[str, Any]],
    resources: List[Union[ResourceStateInput, Dict[str, Any]]],
    risks: List[Union[ProcessRiskInput, Dict[str, Any]]],
) -> DecisionOutcome:
    """Convenience wrapper for DecisionEngine.evaluate_request."""
    engine = DecisionEngine()
    return engine.evaluate_request(request, identity, resources, risks)

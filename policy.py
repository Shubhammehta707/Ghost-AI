import csv
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from dependencies import Record, Evidence, PolicyRule, PolicyFinding

class PolicyEngine:
    def __init__(self, rules_csv_path: str):
        self.rules: Dict[str, PolicyRule] = {}
        self._load_rules(rules_csv_path)

    def _load_rules(self, path: str):
        with open(path, mode='r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rule = PolicyRule(
                    rule_id=row['id'],
                    data_type=row['data_type'],
                    retention_days=int(row['retention_days']),
                    action=row['action'],
                    owner_role=row['owner_role']
                )
                self.rules[rule.data_type] = rule

    def evaluate_record(self, record: Record, evidences: List[Evidence]) -> PolicyFinding:
        rule = self.rules.get(record.data_type)
        if not rule:
            return PolicyFinding(
                record_id=record.record_id,
                rule_id="UNKNOWN",
                action_recommended="FLAG_FOR_REVIEW",
                is_expired=False,
                evidence_ids=[],
                ambiguities=[f"No policy rule found for data type: {record.data_type}"]
            )

        age = (datetime.now() - record.created_at).days
        is_expired = age > rule.retention_days

        evidence_ids = [e.evidence_id for e in evidences if e.record_id == record.record_id]

        return PolicyFinding(
            record_id=record.record_id,
            rule_id=rule.rule_id,
            action_recommended=rule.action if is_expired else "RETAIN",
            is_expired=is_expired,
            evidence_ids=evidence_ids,
            ambiguities=[]
        )

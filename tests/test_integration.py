import unittest
from datetime import datetime, timedelta
from dependencies import Record, Evidence, ResurrectionPath, ResurrectionAnalyzer
from policy import PolicyEngine

class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine("deletion_rules.csv")
        self.analyzer = ResurrectionAnalyzer([])

    def test_full_pipeline(self):
        # 1. Simulate Member 1: Identity-resolved record & evidence
        record = Record("REC-A", "user_data", datetime.now() - timedelta(days=40), "OWNER-1")
        evidence = Evidence("EV-A", "REC-A", "IngestionSource", {}, datetime.now())

        # 2. Member 2: Policy Evaluation
        finding = self.engine.evaluate_record(record, [evidence])

        # 3. Member 2: Dependency check
        paths = [ResurrectionPath("P-A", "IngestionSource", "Database", "sync", "possible", ["EV-A"])]
        self.analyzer.paths = paths
        dependencies = self.analyzer.identify_paths_for_record(record.record_id, [evidence])

        # Verification
        self.assertEqual(finding.record_id, "REC-A")
        self.assertEqual(finding.action_recommended, "delete")
        self.assertEqual(len(dependencies), 1)
        self.assertEqual(dependencies[0].source_system, "IngestionSource")

if __name__ == '__main__':
    unittest.main()

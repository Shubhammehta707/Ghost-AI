import unittest
from datetime import datetime
from dependencies import Evidence, ResurrectionPath, ResurrectionAnalyzer

class TestResurrectionAnalyzer(unittest.TestCase):
    def setUp(self):
        self.paths = [
            ResurrectionPath(
                path_id="PATH-01",
                source_system="ProductionDB",
                destination_system="BackupStore",
                operation="backup",
                status="confirmed_active",
                evidence_ids=["EVID-101"],
                upstream_dependencies=[]
            ),
            ResurrectionPath(
                path_id="PATH-02",
                source_system="BackupStore",
                destination_system="StagingDB",
                operation="restore",
                status="confirmed_active",
                evidence_ids=["EVID-102"],
                upstream_dependencies=["PATH-01"]
            ),
            ResurrectionPath(
                path_id="PATH-03",
                source_system="StagingDB",
                destination_system="ProductionDB",
                operation="sync",
                status="ambiguous",
                evidence_ids=["EVID-103"],
                upstream_dependencies=["PATH-02"]
            )
        ]
        self.analyzer = ResurrectionAnalyzer(self.paths)

    def test_identify_paths(self):
        evidences = [
            Evidence(evidence_id="EVID-101", record_id="REC-001", source_system="ProductionDB", verified_at=datetime.now())
        ]
        matched = self.analyzer.identify_paths_for_record("REC-001", evidences)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].path_id, "PATH-01")

    def test_detect_cycles(self):
        # Introduce cycle: StagingDB -> ProductionDB -> BackupStore -> StagingDB
        cyclic_paths = self.paths + [
            ResurrectionPath(
                path_id="PATH-04",
                source_system="ProductionDB",
                destination_system="BackupStore",
                operation="sync",
                status="confirmed_active",
                evidence_ids=["EVID-104"]
            )
        ]
        analyzer = ResurrectionAnalyzer(cyclic_paths)
        cycles = analyzer.detect_cycles()
        self.assertTrue(len(cycles) > 0)

    def test_remediation_order(self):
        order = self.analyzer.recommend_remediation_order()
        self.assertEqual(order[0].source_system, "ProductionDB")

if __name__ == '__main__':
    unittest.main()

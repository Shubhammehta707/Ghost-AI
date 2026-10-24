import pytest
from datetime import datetime, timedelta
from dependencies import Record, Evidence, ResurrectionPath, ResurrectionAnalyzer
from policy import PolicyEngine

@pytest.fixture
def tmp_csv(tmp_path):
    csv_file = tmp_path / "deletion_rules.csv"
    csv_file.write_text(
        "id,data_type,retention_days,action,owner_role\n"
        "R001,user_data,30,delete,admin\n"
        "R002,audit_log,365,retain,compliance\n"
        "R003,temp_cache,7,redact,system\n"
        "R004,pii_record,90,anonymize,privacy_officer\n"
    )
    return str(csv_file)

def test_policy_treatments_and_mappings(tmp_csv):
    engine = PolicyEngine(tmp_csv)

    # Test delete treatment (expired)
    rec_del = Record("1", "user_data", datetime.now() - timedelta(days=40), "owner1", {})
    finding_del = engine.evaluate_record(rec_del, [])
    assert finding_del.is_expired
    assert finding_del.action_recommended == "delete"
    assert finding_del.rule_id == "R001"

    # Test redact treatment (expired)
    rec_red = Record("2", "temp_cache", datetime.now() - timedelta(days=10), "owner2", {})
    finding_red = engine.evaluate_record(rec_red, [])
    assert finding_red.is_expired
    assert finding_red.action_recommended == "redact"

    # Test anonymize treatment (expired)
    rec_anon = Record("3", "pii_record", datetime.now() - timedelta(days=100), "owner3", {})
    finding_anon = engine.evaluate_record(rec_anon, [])
    assert finding_anon.is_expired
    assert finding_anon.action_recommended == "anonymize"

    # Test retain treatment (not expired)
    rec_ret = Record("4", "audit_log", datetime.now() - timedelta(days=10), "owner4", {})
    finding_ret = engine.evaluate_record(rec_ret, [])
    assert not finding_ret.is_expired
    assert finding_ret.action_recommended == "RETAIN"

def test_missing_policy_information(tmp_csv):
    engine = PolicyEngine(tmp_csv)
    rec = Record("5", "unknown_type", datetime.now(), "owner5", {})
    finding = engine.evaluate_record(rec, [])
    assert finding.action_recommended == "FLAG_FOR_REVIEW"
    assert len(finding.ambiguities) > 0

def test_evidence_preserved_in_results(tmp_csv):
    engine = PolicyEngine(tmp_csv)
    rec = Record("6", "user_data", datetime.now() - timedelta(days=40), "owner6", {})
    ev = Evidence("EV-999", "6", "audit_sys", {}, datetime.now())
    finding = engine.evaluate_record(rec, [ev])
    assert "EV-999" in finding.evidence_ids

def test_resurrection_paths_and_scenarios():
    path_direct = ResurrectionPath(
        path_id="P1",
        source_system="ExtAPI",
        destination_system="MainDB",
        operation="import",
        status="confirmed_active",
        evidence_ids=["EV-1"]
    )
    path_multi = ResurrectionPath(
        path_id="P2",
        source_system="MainDB",
        destination_system="DataWarehouse",
        operation="sync",
        status="confirmed_active",
        evidence_ids=["EV-2"],
        upstream_dependencies=["P1"]
    )
    path_inactive = ResurrectionPath(
        path_id="P3",
        source_system="LegacyStore",
        destination_system="MainDB",
        operation="restore",
        status="inactive",
        evidence_ids=["EV-3"]
    )
    path_ambiguous = ResurrectionPath(
        path_id="P4",
        source_system="UnknownSrc",
        destination_system="MainDB",
        operation="scheduled_job",
        status="ambiguous",
        evidence_ids=[]
    )

    analyzer = ResurrectionAnalyzer([path_direct, path_multi, path_inactive, path_ambiguous])

    # Test direct import/sync path matching via evidence
    evs = [Evidence("EV-1", "REC-1", "ExtAPI", {}, datetime.now())]
    matched = analyzer.identify_paths_for_record("REC-1", evs)
    assert len(matched) == 1
    assert matched[0].path_id == "P1"

    # Test multi-step path and remediation order
    order = analyzer.recommend_remediation_order()
    assert len(order) == 4

    # Test cycle detection
    cyclic_path = ResurrectionPath(
        path_id="P_CYCLE",
        source_system="MainDB",
        destination_system="ExtAPI",
        operation="sync",
        status="confirmed_active",
        evidence_ids=["EV-4"]
    )
    cyclic_analyzer = ResurrectionAnalyzer([path_direct, cyclic_path])
    cycles = cyclic_analyzer.detect_cycles()
    assert len(cycles) > 0

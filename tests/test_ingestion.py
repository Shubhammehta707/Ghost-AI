import os
import tempfile
import pytest
from ingestion import load_deletion_requests, load_deletion_rules, IngestedDataset, ingest_all_data

def test_missing_files_raise_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(FileNotFoundError, match="Missing required file"):
            load_deletion_requests(os.path.join(tmpdir, "nonexistent.csv"))

        with pytest.raises(FileNotFoundError, match="Missing required file"):
            load_deletion_rules(os.path.join(tmpdir, "nonexistent.csv"))

def test_successful_ingestion():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fixtures
        req_path = os.path.join(tmpdir, "deletion_requests.csv")
        rule_path = os.path.join(tmpdir, "deletion_rules.csv")

        with open(req_path, 'w') as f:
            f.write("request_id,user_id,email,phone,request_timestamp,scope,status\n")
            f.write("r1,u1,test@test.com,12345,2026-10-24T12:00:00,FULL,PENDING\n")

        with open(rule_path, 'w') as f:
            f.write("rule_id,jurisdiction,data_category,retention_period_days,exemption_reason,priority\n")
            f.write("rule1,GDPR,PII,30,NONE,1\n")

        data = ingest_all_data(tmpdir)

        assert len(data.deletion_requests) == 1
        assert len(data.deletion_rules) == 1
        assert data.deletion_requests[0].user_id == "u1"

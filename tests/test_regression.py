import pytest
import os
import tempfile
from ingestion import ingest_all_data, load_deletion_requests
from identity import normalize_phone, resolve_identities

def test_phone_normalization_international():
    # +1 555 and 1 555 should probably match if we are smart,
    # but at least + should be preserved to distinguish international.
    assert normalize_phone("+1 555") == "+1555"
    assert normalize_phone("1 555") == "1555"
    assert normalize_phone("+44 20") == "+4420"

def test_media_user_linkage():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a user directory in media
        media_user_dir = os.path.join(tmpdir, "media", "u123")
        os.makedirs(media_user_dir)
        with open(os.path.join(media_user_dir, "photo.jpg"), "w") as f:
            f.write("data")

        # Create CSVs
        req_path = os.path.join(tmpdir, "deletion_requests.csv")
        rule_path = os.path.join(tmpdir, "deletion_rules.csv")
        with open(req_path, 'w') as f:
            f.write("request_id,user_id,email,phone,request_timestamp,scope,status\n")
            f.write("r1,u123,,,2026-10-24T12:00:00,FULL,PENDING\n")
        with open(rule_path, 'w') as f:
            f.write("rule_id,jurisdiction,data_category,retention_period_days,exemption_reason,priority\n")
            f.write("rule1,GDPR,PII,30,NONE,1\n")

        dataset = ingest_all_data(tmpdir)

        # Verify media is linked to u123
        # Currently, this will FAIL because ingestion.py doesn't link them yet.
        found_media = False
        for record in dataset.media_records:
            if "u123" in record.associated_user_ids:
                found_media = True
        assert found_media, "Media in u123/ directory should be linked to user u123"

def test_duplicate_request_ids():
    with tempfile.TemporaryDirectory() as tmpdir:
        req_path = os.path.join(tmpdir, "deletion_requests.csv")
        with open(req_path, 'w') as f:
            f.write("request_id,user_id,email,phone,request_timestamp,scope,status\n")
            f.write("r1,u1,,,2026-10-24T12:00:00,FULL,PENDING\n")
            f.write("r1,u2,,,2026-10-24T12:00:00,FULL,PENDING\n")

        # This should probably raise a warning or handle it.
        # If the requirement is "Duplicate request IDs overwriting dictionary entries",
        # we should ensure we don't just lose data.
        requests = load_deletion_requests(req_path)
        ids = [r.request_id for r in requests]
        assert len(ids) == 2
        assert len(set(ids)) == 1 # They are duplicates

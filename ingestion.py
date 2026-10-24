import csv
import os
import pathlib
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from datetime import datetime

# --- Data Structures ---

@dataclass
class DeletionRequest:
    request_id: str
    user_id: str
    email: Optional[str]
    phone: Optional[str]
    request_timestamp: datetime
    scope: str
    status: str

@dataclass
class DeletionRule:
    rule_id: str
    jurisdiction: str
    data_category: str
    retention_period_days: int
    exemption_reason: str
    priority: int

@dataclass
class MediaRecord:
    media_id: str  # Deterministic: sha256 of file path
    file_path: str
    file_type: str
    associated_user_ids: Set[str] = field(default_factory=set)

@dataclass
class IngestedDataset:
    deletion_requests: List[DeletionRequest] = field(default_factory=list)
    deletion_rules: List[DeletionRule] = field(default_factory=list)
    media_records: List[MediaRecord] = field(default_factory=list)

# --- Ingestion Logic ---

def _get_deterministic_id(file_path: str) -> str:
    return hashlib.sha256(file_path.encode('utf-8')).hexdigest()

def load_deletion_requests(file_path: str) -> List[DeletionRequest]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Missing required file: {file_path}")

    requests = []
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            requests.append(DeletionRequest(
                request_id=row['request_id'],
                user_id=row['user_id'],
                email=row.get('email'),
                phone=row.get('phone'),
                request_timestamp=datetime.fromisoformat(row['request_timestamp']),
                scope=row['scope'],
                status=row['status']
            ))
    return requests

def load_deletion_rules(file_path: str) -> List[DeletionRule]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Missing required file: {file_path}")

    rules = []
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rules.append(DeletionRule(
                rule_id=row['rule_id'],
                jurisdiction=row['jurisdiction'],
                data_category=row['data_category'],
                retention_period_days=int(row['retention_period_days']),
                exemption_reason=row['exemption_reason'],
                priority=int(row['priority'])
            ))
    return rules

def ingest_all_data(data_dir: str) -> IngestedDataset:
    """
    Ingests GhostTrace AI datasets.
    Raises FileNotFoundError if required files are missing.
    """
    dataset = IngestedDataset()

    # Load Tables
    dataset.deletion_requests = load_deletion_requests(os.path.join(data_dir, "deletion_requests.csv"))
    dataset.deletion_rules = load_deletion_rules(os.path.join(data_dir, "deletion_rules.csv"))

    # Scan Media
    media_dir = os.path.join(data_dir, "media")
    if os.path.exists(media_dir):
        for root, _, files in os.walk(media_dir):
            for file in files:
                path = os.path.join(root, file)
                record = MediaRecord(
                    media_id=_get_deterministic_id(path),
                    file_path=path,
                    file_type=pathlib.Path(file).suffix.lower()
                )
                # Heuristic: Check if immediate parent directory is a user_id
                parent_dir = os.path.basename(root)
                if parent_dir != "media":
                    record.associated_user_ids.add(parent_dir)
                dataset.media_records.append(record)

    return dataset

# --- Simple Testing Harness ---

def run_smoke_test():
    """Runs tests on synthetic data fixtures."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create dummy data
        req_path = os.path.join(tmpdir, "deletion_requests.csv")
        rule_path = os.path.join(tmpdir, "deletion_rules.csv")

        with open(req_path, 'w') as f:
            f.write("request_id,user_id,email,phone,request_timestamp,scope,status\n")
            f.write("r1,u1,test@test.com,12345,2026-10-24T12:00:00,FULL,PENDING\n")

        with open(rule_path, 'w') as f:
            f.write("rule_id,jurisdiction,data_category,retention_period_days,exemption_reason,priority\n")
            f.write("rule1,GDPR,PII,30,NONE,1\n")

        # Test Ingestion
        data = ingest_all_data(tmpdir)

        assert len(data.deletion_requests) == 1, "Failed: Request count mismatch"
        assert len(data.deletion_rules) == 1, "Failed: Rule count mismatch"
        assert data.deletion_requests[0].request_id == "r1"

        print("Smoke test passed: Ingested synthetic fixtures.")

if __name__ == "__main__":
    try:
        run_smoke_test()
    except Exception as e:
        print(f"Smoke test failed: {e}")

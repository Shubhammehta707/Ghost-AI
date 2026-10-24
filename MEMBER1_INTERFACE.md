# Member 1: Ingestion & Identity Resolution Interface

This document specifies the public data structures and functions provided by Member 1 for use by Member 2 (Deletion Engine).

## Core Data Structures

### `IdentityMatch`
Represents an individual piece of evidence linking an identifier to a user.
- `identifier_type`: `'user_id' | 'email' | 'phone'`
- `identifier_value`: Normalized string value.
- `match_confidence`: `'CONFIRMED'` (unique link) or `'AMBIGUOUS'` (shared with another user).
- `source_request_id`: The `request_id` from the ingestion layer that provided this link.
- `explanation`: Context on the match (e.g., `"Primary user identifier"`, or `"Shared with: u2"`).

### `ResolvedIdentity`
Represents the unified identity profile for a user.
- `canonical_user_id`: The primary user ID.
- `emails`: `Set[str]` of all normalized emails associated with this user.
- `phones`: `Set[str]` of all normalized phone numbers associated with this user.
- `matches`: `List[IdentityMatch]` containing provenance for every link.

## Public Functions

### `resolve_identities(dataset: IngestedDataset) -> Dict[str, ResolvedIdentity]`
Processes all deletion requests in the ingested dataset and groups them by user ID.

```python
from ingestion import ingest_all_data
from identity import resolve_identities

# 1. Ingest Data
dataset = ingest_all_data("path/to/data")

# 2. Resolve Identities
identities = resolve_identities(dataset)

# 3. Access for Deletion Logic
for user_id, identity in identities.items():
    print(f"User: {user_id}")
    print(f"Emails: {identity.emails}")
    
    # Check for ambiguities before deleting!
    for match in identity.matches:
        if match.match_confidence == 'AMBIGUOUS':
            print(f"WARNING: Ambiguous {match.identifier_type}: {match.identifier_value}")
```

## Synthetic Example for Member 2

```python
from ingestion import DeletionRequest, IngestedDataset
from identity import resolve_identities
from datetime import datetime

# Setup synthetic data
req1 = DeletionRequest(
    request_id="req_001",
    user_id="user_A",
    email="alice@example.com",
    phone="+15550001",
    request_timestamp=datetime.now(),
    scope="FULL",
    status="PENDING"
)
req2 = DeletionRequest(
    request_id="req_002",
    user_id="user_B",
    email="alice@example.com", # Colliding email!
    phone="+15550002",
    request_timestamp=datetime.now(),
    scope="FULL",
    status="PENDING"
)

dataset = IngestedDataset(deletion_requests=[req1, req2])
resolved = resolve_identities(dataset)

# user_A's email will be marked as AMBIGUOUS
user_a_email_match = next(m for m in resolved["user_A"].matches if m.identifier_type == "email")
assert user_a_email_match.match_confidence == "AMBIGUOUS"
assert "Shared with: user_B" in user_a_email_match.explanation
```

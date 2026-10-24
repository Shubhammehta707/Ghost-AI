import pytest
from datetime import datetime
from ingestion import DeletionRequest, IngestedDataset
from identity import (
    normalize_email, normalize_phone, resolve_identities,
    ResolvedIdentity, IdentityMatch
)

def test_normalization():
    assert normalize_email(" TEST@Example.com ") == "test@example.com"
    assert normalize_email("not-an-email") is None
    assert normalize_email(None) is None

    assert normalize_phone("+1 (555) 123-4567") == "+15551234567"
    assert normalize_phone("123-456") == "123456"
    assert normalize_phone(None) is None

def test_identity_resolution_basic():
    req1 = DeletionRequest(
        request_id="r1", user_id="u1", email="user1@test.com",
        phone="111", request_timestamp=datetime.now(), scope="FULL", status="PENDING"
    )
    dataset = IngestedDataset(deletion_requests=[req1])

    resolved = resolve_identities(dataset)
    assert "u1" in resolved
    ident = resolved["u1"]
    assert "user1@test.com" in ident.emails
    assert "111" in ident.phones

    # Check matches
    u_match = next(m for m in ident.matches if m.identifier_type == "user_id")
    assert u_match.match_confidence == "CONFIRMED"
    assert u_match.identifier_value == "u1"

def test_historical_identifiers():
    # User u1 has two requests with different emails (historical change)
    req1 = DeletionRequest(
        request_id="r1", user_id="u1", email="old@test.com",
        phone=None, request_timestamp=datetime.now(), scope="FULL", status="PENDING"
    )
    req2 = DeletionRequest(
        request_id="r2", user_id="u1", email="new@test.com",
        phone=None, request_timestamp=datetime.now(), scope="FULL", status="PENDING"
    )
    dataset = IngestedDataset(deletion_requests=[req1, req2])

    resolved = resolve_identities(dataset)
    ident = resolved["u1"]
    assert "old@test.com" in ident.emails
    assert "new@test.com" in ident.emails
    assert len(ident.emails) == 2

    # Verify evidence references
    m_old = next(m for m in ident.matches if m.identifier_value == "old@test.com")
    m_new = next(m for m in ident.matches if m.identifier_value == "new@test.com")
    assert m_old.source_request_id == "r1"
    assert m_new.source_request_id == "r2"

def test_ambiguous_matches():
    # Two different users share the same phone number (Ambiguous)
    req1 = DeletionRequest(
        request_id="r1", user_id="u1", email="u1@test.com",
        phone="555", request_timestamp=datetime.now(), scope="FULL", status="PENDING"
    )
    req2 = DeletionRequest(
        request_id="r2", user_id="u2", email="u2@test.com",
        phone="555", request_timestamp=datetime.now(), scope="FULL", status="PENDING"
    )
    dataset = IngestedDataset(deletion_requests=[req1, req2])

    resolved = resolve_identities(dataset)

    # Check u1
    m1 = next(m for m in resolved["u1"].matches if m.identifier_type == "phone")
    assert m1.match_confidence == "AMBIGUOUS"
    assert "Shared with: u2" in m1.explanation

    # Check u2
    m2 = next(m for m in resolved["u2"].matches if m.identifier_type == "phone")
    assert m2.match_confidence == "AMBIGUOUS"
    assert "Shared with: u1" in m2.explanation

def test_missing_identifiers():
    req1 = DeletionRequest(
        request_id="r1", user_id="u1", email=None,
        phone=None, request_timestamp=datetime.now(), scope="FULL", status="PENDING"
    )
    dataset = IngestedDataset(deletion_requests=[req1])

    resolved = resolve_identities(dataset)
    ident = resolved["u1"]
    assert len(ident.emails) == 0
    assert len(ident.phones) == 0
    assert len(ident.matches) == 1 # Only user_id match

def test_duplicate_records():
    # Identical requests shouldn't create duplicate entries in ResolvedIdentity sets
    req1 = DeletionRequest(
        request_id="r1", user_id="u1", email="u1@test.com",
        phone="123", request_timestamp=datetime.now(), scope="FULL", status="PENDING"
    )
    req2 = DeletionRequest(
        request_id="r2", user_id="u1", email="u1@test.com",
        phone="123", request_timestamp=datetime.now(), scope="FULL", status="PENDING"
    )
    dataset = IngestedDataset(deletion_requests=[req1, req2])

    resolved = resolve_identities(dataset)
    ident = resolved["u1"]
    assert len(ident.emails) == 1
    assert len(ident.phones) == 1
    # Note: identity.py logic for matches might have duplicates if not careful,
    # but the sets (ident.emails, ident.phones) handle the core duplication.
    # The current implementation iterates over the sets to create matches, so it should be fine.
    email_matches = [m for m in ident.matches if m.identifier_type == "email"]
    assert len(email_matches) == 1

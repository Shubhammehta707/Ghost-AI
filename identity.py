import re
from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field
from ingestion import IngestedDataset, DeletionRequest

@dataclass
class IdentityMatch:
    identifier_type: str  # 'email', 'phone', 'user_id'
    identifier_value: str
    match_confidence: str  # 'CONFIRMED', 'AMBIGUOUS'
    source_request_id: str
    explanation: str

@dataclass
class ResolvedIdentity:
    canonical_user_id: str
    emails: Set[str] = field(default_factory=set)
    phones: Set[str] = field(default_factory=set)
    matches: List[IdentityMatch] = field(default_factory=list)

def normalize_email(email: Optional[str]) -> Optional[str]:
    """Normalizes email addresses to lowercase and strips whitespace."""
    if not email or not isinstance(email, str) or '@' not in email:
        return None
    return email.strip().lower()

def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Normalizes phone numbers by removing all non-numeric characters except leading +."""
    if not phone or not isinstance(phone, str):
        return None
    phone = phone.strip()
    has_plus = phone.startswith('+')
    digits = re.sub(r'\D', '', phone)
    if not digits:
        return None
    return f"+{digits}" if has_plus else digits

def resolve_identities(dataset: IngestedDataset) -> Dict[str, ResolvedIdentity]:
    """
    Resolves user identities based on identifiers found in deletion requests.
    Identifies confirmed links and flags ambiguous overlaps.
    """
    user_map: Dict[str, ResolvedIdentity] = {}
    email_to_users: Dict[str, Set[str]] = {}
    phone_to_users: Dict[str, Set[str]] = {}

    # First pass: Build maps and collect all identifiers
    for req in dataset.deletion_requests:
        uid = req.user_id
        if not uid:
            continue

        if uid not in user_map:
            user_map[uid] = ResolvedIdentity(canonical_user_id=uid)
            user_map[uid].matches.append(IdentityMatch(
                identifier_type='user_id',
                identifier_value=uid,
                match_confidence='CONFIRMED',
                source_request_id=req.request_id,
                explanation="Primary user identifier"
            ))

        ident = user_map[uid]

        email = normalize_email(req.email)
        if email:
            ident.emails.add(email)
            if email not in email_to_users:
                email_to_users[email] = set()
            email_to_users[email].add(uid)

        phone = normalize_phone(req.phone)
        if phone:
            ident.phones.add(phone)
            if phone not in phone_to_users:
                phone_to_users[phone] = set()
            phone_to_users[phone].add(uid)

    # Second pass: Determine confidence and add matches
    for uid, ident in user_map.items():
        # Process Emails
        for email in sorted(list(ident.emails)):
            users_sharing_email = email_to_users.get(email, set())
            is_ambiguous = len(users_sharing_email) > 1

            # Find the first request that provided this email for this user
            source_req = next(
                (r for r in dataset.deletion_requests if r.user_id == uid and normalize_email(r.email) == email),
                None
            )
            req_id = source_req.request_id if source_req else "unknown"

            confidence = 'AMBIGUOUS' if is_ambiguous else 'CONFIRMED'
            explanation = f"Email linked to user_id in request {req_id}"
            if is_ambiguous:
                others = sorted(list(users_sharing_email - {uid}))
                explanation += f" (Shared with: {', '.join(others)})"

            ident.matches.append(IdentityMatch(
                identifier_type='email',
                identifier_value=email,
                match_confidence=confidence,
                source_request_id=req_id,
                explanation=explanation
            ))

        # Process Phones
        for phone in sorted(list(ident.phones)):
            users_sharing_phone = phone_to_users.get(phone, set())
            is_ambiguous = len(users_sharing_phone) > 1

            source_req = next(
                (r for r in dataset.deletion_requests if r.user_id == uid and normalize_phone(r.phone) == phone),
                None
            )
            req_id = source_req.request_id if source_req else "unknown"

            confidence = 'AMBIGUOUS' if is_ambiguous else 'CONFIRMED'
            explanation = f"Phone linked to user_id in request {req_id}"
            if is_ambiguous:
                others = sorted(list(users_sharing_phone - {uid}))
                explanation += f" (Shared with: {', '.join(others)})"

            ident.matches.append(IdentityMatch(
                identifier_type='phone',
                identifier_value=phone,
                match_confidence=confidence,
                source_request_id=req_id,
                explanation=explanation
            ))

    return user_map

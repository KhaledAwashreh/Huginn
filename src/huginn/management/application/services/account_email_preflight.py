"""Identify ownership conflicts before enabling email sign-in."""

from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from huginn.management.application.read_models.account_email_candidate import (
    AccountEmailCandidate,
)

_FOUNDER_PLACEHOLDERS = {"khaled@huginn.local", "craig@huginn.local"}
BLOCKING_ISSUES = frozenset(
    {
        "candidate_uses_another_contact",
        "duplicate_candidate",
        "founder_placeholder",
        "missing_or_invalid_sign_in_email",
        "missing_recovery_identity",
        "missing_user",
    }
)


def find_account_email_issues(
    candidates: Iterable[AccountEmailCandidate],
) -> dict[UUID, tuple[str, ...]]:
    issues: defaultdict[UUID, set[str]] = defaultdict(set)
    targets: defaultdict[str, set[UUID]] = defaultdict(set)
    contacts: defaultdict[str, set[UUID]] = defaultdict(set)
    for candidate in candidates:
        account_id = candidate.account_id
        target = candidate.sign_in_email
        contact = (candidate.contact_email or "").strip().lower()
        if contact:
            contacts[contact].add(account_id)
        if not candidate.has_user:
            issues[account_id].add("missing_user")
        if candidate.verification_required is None:
            issues[account_id].add("missing_recovery_identity")
        if target is None:
            issues[account_id].add("missing_or_invalid_sign_in_email")
            continue

        targets[target].add(account_id)
        if target in _FOUNDER_PLACEHOLDERS:
            issues[account_id].add("founder_placeholder")
        elif contact in _FOUNDER_PLACEHOLDERS:
            issues[account_id].add("legacy_founder_placeholder")
        if target != contact:
            if candidate.verified_email is not None:
                issues[account_id].add("verified_contact_mismatch")
            elif candidate.verification_required:
                issues[account_id].add("pending_signup_contact_mismatch")
        elif (
            candidate.verified_email is None
            and not candidate.verification_required
            and candidate.pending_email is not None
            and candidate.pending_email.strip().lower() != contact
        ):
            issues[account_id].add("pending_contact_mismatch")

    for email, owners in targets.items():
        for account_id in owners:
            if len(owners) > 1:
                issues[account_id].add("duplicate_candidate")
            if contacts[email] - {account_id}:
                issues[account_id].add("candidate_uses_another_contact")
    return {account_id: tuple(sorted(found)) for account_id, found in issues.items()}

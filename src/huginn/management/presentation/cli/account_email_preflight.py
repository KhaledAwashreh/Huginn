"""Audit legacy account addresses before enabling email sign-in."""

import argparse
import json
import os
from collections.abc import Callable

from huginn.management.application.read_models.account_email_candidate import (
    AccountEmailCandidate,
)
from huginn.management.application.services.account_email_preflight import (
    BLOCKING_ISSUES,
    find_account_email_issues,
)
from huginn.management.persistence.errors.database import DatabaseError


def main(
    argv: list[str] | None = None,
    *,
    candidates_factory: Callable[[str], tuple[AccountEmailCandidate, ...]],
    database_url: str | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-addresses",
        action="store_true",
        help="Include private email addresses for accounts with findings",
    )
    args = parser.parse_args(argv)
    if database_url is None:
        database_url = os.environ.get("HUGINN_MANAGEMENT_DATABASE_URL", "")
    database_url = database_url.strip()
    if not database_url:
        print(json.dumps({"error": "management_database_url_missing"}))
        return 1
    try:
        candidates = candidates_factory(database_url)
    except DatabaseError:
        print(json.dumps({"error": "account_email_preflight_unavailable"}))
        return 1

    issues = find_account_email_issues(candidates)
    findings: list[dict[str, object]] = []
    blocked_accounts = 0
    for candidate in candidates:
        finding_issues = issues.get(candidate.account_id)
        if finding_issues is None:
            continue
        blocked = not BLOCKING_ISSUES.isdisjoint(finding_issues)
        blocked_accounts += int(blocked)
        finding: dict[str, object] = {
            "account_id": str(candidate.account_id),
            "blocking": blocked,
            "issues": finding_issues,
        }
        if args.include_addresses:
            finding["addresses"] = {
                "candidate": candidate.sign_in_email,
                "contact": candidate.contact_email,
                "pending": candidate.pending_email,
                "verified": candidate.verified_email,
            }
        findings.append(finding)
    print(
        json.dumps(
            {
                "accounts_checked": len(candidates),
                "blocked_accounts": blocked_accounts,
                "findings": findings,
            }
        )
    )
    return 2 if blocked_accounts else 0

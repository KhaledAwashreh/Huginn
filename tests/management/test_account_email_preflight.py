import json
from uuid import uuid4

import psycopg

from huginn.management.account_email_preflight import main
from tests.postgres_harness import provisioned_postgres


def _account(connection, *, contact=None, verified=None, pending=None, required=False):
    account_id = uuid4()
    connection.execute(
        "INSERT INTO operational.accounts (id, username, password_hash) "
        "VALUES (%s, %s, 'retained-hash')",
        (account_id, str(account_id)),
    )
    if contact is not None:
        connection.execute(
            "INSERT INTO operational.users "
            "(account_id, first_name, last_name, email, phone_number, country_of_residence) "
            "VALUES (%s, 'Test', 'Owner', %s, '+12025550100', 'US')",
            (account_id, contact),
        )
    connection.execute(
        "INSERT INTO operational.account_recovery_identity "
        "(account_id, verification_required, pending_email, verified_email, verified_at) "
        "VALUES (%s, %s, %s, %s, CASE WHEN %s::text IS NULL THEN NULL ELSE now() END)",
        (account_id, required, pending, verified, verified),
    )
    return str(account_id)


def _snapshot(connection):
    return connection.execute(
        "SELECT to_jsonb(a), to_jsonb(u), to_jsonb(r) "
        "FROM operational.accounts a "
        "LEFT JOIN operational.users u ON u.account_id = a.id "
        "LEFT JOIN operational.account_recovery_identity r ON r.account_id = a.id "
        "ORDER BY a.id"
    ).fetchall()


def test_cutover_preflight_flags_legacy_conflicts_without_disclosing_or_editing_addresses(
    capsys,
):
    with (
        provisioned_postgres("huginn_email_preflight") as database_url,
        psycopg.connect(database_url, autocommit=True) as connection,
    ):
        _account(connection, contact="clean@example.test")
        assert main([], database_url=database_url) == 0
        assert json.loads(capsys.readouterr().out) == {
            "accounts_checked": 1,
            "blocked_accounts": 0,
            "findings": [],
        }

        verified = _account(
            connection, contact="old@example.test", verified="shared@example.test"
        )
        owner = _account(connection, contact="Shared@example.test")
        pending = _account(
            connection,
            contact="unverified@example.test",
            pending="pending@example.test",
            required=True,
        )
        founder = _account(connection, contact="craig@huginn.local")
        malformed = _account(connection, contact="bad-address")
        userless = _account(connection)
        before = _snapshot(connection)

        assert main([], database_url=database_url) == 2
        output = capsys.readouterr().out
        assert "@" not in output
        report = json.loads(output)
        findings = {row["account_id"]: set(row["issues"]) for row in report["findings"]}
        assert report["accounts_checked"] == 7
        assert report["blocked_accounts"] == 5
        assert findings == {
            verified: {
                "candidate_uses_another_contact",
                "duplicate_candidate",
                "verified_contact_mismatch",
            },
            owner: {"duplicate_candidate"},
            pending: {"pending_signup_contact_mismatch"},
            founder: {"founder_placeholder"},
            malformed: {"missing_or_invalid_sign_in_email"},
            userless: {"missing_user", "missing_or_invalid_sign_in_email"},
        }

        assert main(["--include-addresses"], database_url=database_url) == 2
        report = json.loads(capsys.readouterr().out)
        rows = {row["account_id"]: row for row in report["findings"]}
        assert rows[verified]["addresses"] == {
            "candidate": "shared@example.test",
            "contact": "old@example.test",
            "pending": None,
            "verified": "shared@example.test",
        }
        assert rows[pending]["addresses"]["candidate"] == "pending@example.test"
        assert _snapshot(connection) == before

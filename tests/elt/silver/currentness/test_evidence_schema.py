"""Guarded current context and durable Match evidence schema contract."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from tests.postgres_harness import SCHEMA_DIR, provisioned_postgres

MIGRATION = SCHEMA_DIR / "gold-current-source-evidence.sql"
EVENT = datetime(2025, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="module")
def evidence_database_url() -> Iterator[str]:
    with provisioned_postgres("huginn_evidence") as url:
        yield url


def _seed_current(
    connection: psycopg.Connection,
    *,
    source: str = "yc",
    hiring_state: str = "true",
    listing_state: str = "available",
    identity_state: str = "consistent",
    occurred_at: datetime | None = EVENT,
) -> tuple[str, str, object, object]:
    stable_id = f"{source}-{uuid4().hex}"
    domain = f"{uuid4().hex}.example.test"
    payload = {
        "id": stable_id,
        "website": f"https://{domain}",
    }
    if hiring_state in ("true", "false"):
        payload["isHiring"] = hiring_state == "true"
    bronze_table = (
        "bronze.web_scrape_ingest" if source == "eu_startups" else "bronze.api_ingest"
    )
    connection.execute(
        f"""INSERT INTO {bronze_table}
            (source, stable_id, payload, content_hash, run_id)
            VALUES (%s, %s, %s, 'unchanged-content-hash', %s)""",
        (source, stable_id, psycopg.types.json.Jsonb(payload), uuid4()),
    )
    company_id = connection.execute(
        "INSERT INTO gold.company (domain, name) VALUES (%s, 'Company') RETURNING id",
        (domain,),
    ).fetchone()[0]
    connection.execute(
        """INSERT INTO silver.resolved_signals
           (source, source_stable_id, resolved_company_key, company_name_raw,
            signal_type, key_derivation)
           VALUES (%s, %s, %s, 'Source company', 'other', 'domain_normalized')""",
        (source, stable_id, domain),
    )
    gold_id = connection.execute(
        """INSERT INTO gold.company_signal
           (company_id, source, source_stable_id, signal_type, occurred_at,
            description)
           VALUES (%s, %s, %s, 'other', %s, 'stale gold label') RETURNING id""",
        (company_id, source, stable_id, EVENT),
    ).fetchone()[0]
    parser = {
        "hn": "hn-context-v1",
        "yc": "yc-context-v1",
        "eu_startups": "eu-startups-context-v1",
    }[source]
    snapshot_id = connection.execute(
        """INSERT INTO silver.source_context_snapshot
           (source, stable_id, source_url, payload_sha256, parser_version,
            normalized_text, source_fields)
           VALUES (%s, %s, 'https://source.example/item', repeat('a', 64), %s,
                   'Current normalized context', '{"stage":"Seed stage"}')
           RETURNING id""",
        (source, stable_id, parser),
    ).fetchone()[0]
    observation_id = connection.execute(
        f"""INSERT INTO silver.source_lifecycle_observation
           (source, stable_id, raw_token, resolution_token, policy_version,
            context_version, snapshot_id, listing_state, hiring_state,
            identity_state, reason, explicit_domain, resolved_company_key,
            key_derivation, company_id, occurred_at, bronze_fetched_at,
            bronze_last_checked_at)
           SELECT %s, %s, md5(b.payload::text),
                  md5(jsonb_build_array(r.resolved_company_key,
                                        r.key_derivation)::text),
                  'source-lifecycle-v1', %s, %s, %s, %s, %s, 'seeded',
                  %s, %s, 'domain_normalized', %s, %s, b.fetched_at,
                  b.last_checked_at
           FROM {bronze_table} b JOIN silver.resolved_signals r
               ON r.source = b.source AND r.source_stable_id = b.stable_id
           WHERE b.source = %s AND b.stable_id = %s RETURNING id""",
        (
            source,
            stable_id,
            parser,
            snapshot_id,
            listing_state,
            hiring_state,
            identity_state,
            domain,
            domain,
            company_id,
            occurred_at,
            source,
            stable_id,
        ),
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO silver.source_currentness (source, stable_id, current_observation_id) VALUES (%s, %s, %s)",
        (source, stable_id, observation_id),
    )
    username = f"evidence-{uuid4().hex}"
    account_id = connection.execute(
        "INSERT INTO operational.accounts (username, password_hash) VALUES (%s, 'test') RETURNING id",
        (username,),
    ).fetchone()[0]
    user_id = connection.execute(
        """INSERT INTO operational.users
           (account_id, first_name, last_name, email, phone_number,
            country_of_residence)
           VALUES (%s, 'Evidence', 'Tester', %s, '000', 'Test') RETURNING id""",
        (account_id, f"{username}@example.test"),
    ).fetchone()[0]
    match_id = connection.execute(
        "INSERT INTO operational.match (user_id, company_id) VALUES (%s, %s) RETURNING id",
        (user_id, company_id),
    ).fetchone()
    return stable_id, domain, gold_id, (observation_id, match_id[0], company_id)


def test_migration_is_canonical_additive_and_idempotent(evidence_database_url: str):
    from tests.postgres_harness import BASE_SCHEMA_FILES, SCHEMA_FILES

    assert MIGRATION.is_file()
    assert SCHEMA_FILES.count(MIGRATION.name) == 1
    assert SCHEMA_FILES.index(MIGRATION.name) > SCHEMA_FILES.index(
        "silver-source-currentness.sql"
    )
    with psycopg.connect(evidence_database_url, autocommit=True) as connection:
        before = connection.execute("SELECT count(*) FROM gold.company").fetchone()[0]
        connection.execute(MIGRATION.read_text())
        assert (
            connection.execute("SELECT count(*) FROM gold.company").fetchone()[0]
            == before
        )
        assert connection.execute(
            "SELECT to_regclass('gold.current_source_evidence')"
        ).fetchone()[0]
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.match_source_evidence"
            ).fetchone()[0]
            == 0
        )
        assert BASE_SCHEMA_FILES[-1] == "operational.sql"


def test_migration_rejects_incompatible_existing_history_shape():
    from tests.postgres_harness import BASE_SCHEMA_FILES

    with (
        provisioned_postgres("huginn_evidence_upgrade", apply_schema=False) as url,
        psycopg.connect(url, autocommit=True) as connection,
    ):
        for filename in BASE_SCHEMA_FILES:
            connection.execute((SCHEMA_DIR / filename).read_text())
        connection.execute((SCHEMA_DIR / "silver-source-currentness.sql").read_text())
        connection.execute(
            "CREATE TABLE operational.match_source_evidence (match_id UUID)"
        )
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="incompatible match source evidence columns",
        ):
            connection.execute(MIGRATION.read_text())


def test_current_view_uses_guarded_context_and_safe_labels(evidence_database_url: str):
    with psycopg.connect(evidence_database_url) as connection:
        seeded = [
            _seed_current(connection, source="yc", hiring_state="true"),
            _seed_current(connection, source="yc", hiring_state="false"),
            _seed_current(connection, source="yc", hiring_state="unknown"),
            _seed_current(connection, source="eu_startups", hiring_state="false"),
            _seed_current(connection, source="hn", hiring_state="true"),
        ]
        rows = connection.execute(
            """SELECT source_stable_id, source, signal_type, evidence_kind,
                      hiring_state, description, source_url, stage, occurred_at
               FROM gold.current_source_evidence
               WHERE source_stable_id = ANY(%s) ORDER BY source""",
            ([item[0] for item in seeded],),
        ).fetchall()
        labels = {row[0]: row[1:5] for row in rows}
        assert labels == {
            seeded[0][0]: ("yc", "hiring", "hiring", "true"),
            seeded[1][0]: ("yc", "other", "directory_context", "false"),
            seeded[2][0]: ("yc", "other", "directory_context", "unknown"),
            seeded[3][0]: ("eu_startups", "other", "directory_context", "false"),
            seeded[4][0]: ("hn", "hiring", "hiring", "true"),
        }
        assert all(
            row[5:8]
            == (
                "Current normalized context",
                "https://source.example/item",
                "Seed stage",
            )
            for row in rows
        )
        assert all(row[8] == EVENT for row in rows)


def test_current_view_rejects_raw_resolution_and_gold_drift(evidence_database_url: str):
    with psycopg.connect(evidence_database_url) as connection:
        stable_id, domain, gold_id, (_observation_id, _match_id, _company_id) = (
            _seed_current(connection)
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 1
        )

        connection.execute(
            "UPDATE bronze.api_ingest SET last_checked_at = last_checked_at + interval '1 minute' WHERE stable_id = %s",
            (stable_id,),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 1
        )
        connection.execute(
            "UPDATE bronze.api_ingest SET fetched_at = fetched_at + interval '1 second' WHERE stable_id = %s",
            (stable_id,),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 1
        )
        connection.execute(
            "UPDATE bronze.api_ingest SET payload = payload || '{\"changed\":true}'::jsonb WHERE stable_id = %s",
            (stable_id,),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 0
        )
        connection.execute(
            "UPDATE bronze.api_ingest SET payload = payload - 'changed' WHERE stable_id = %s",
            (stable_id,),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 1
        )

        connection.execute(
            "UPDATE silver.resolved_signals SET resolved_company_key = %s WHERE source_stable_id = %s",
            (f"other-{uuid4().hex}.test", stable_id),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 0
        )
        connection.execute(
            "UPDATE silver.resolved_signals SET resolved_company_key = %s WHERE source_stable_id = %s",
            (domain, stable_id),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 1
        )
        other_domain = f"other-{uuid4().hex}.test"
        connection.execute(
            "UPDATE gold.company SET domain = %s WHERE id = %s",
            (other_domain, _company_id),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 0
        )
        connection.execute(
            "UPDATE gold.company SET domain = %s WHERE id = %s",
            (domain, _company_id),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 1
        )
        other_company_id = connection.execute(
            "INSERT INTO gold.company (domain, name) VALUES (%s, 'Other') RETURNING id",
            (f"other-{uuid4().hex}.test",),
        ).fetchone()[0]
        connection.execute(
            "UPDATE gold.company_signal SET company_id = %s WHERE id = %s",
            (other_company_id, gold_id),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 0
        )


def test_view_rejects_unexpected_policy_and_parser_versions(evidence_database_url: str):
    with psycopg.connect(evidence_database_url) as connection:
        stable_id, _domain, _gold, (observation_id, _match_id, _company_id) = (
            _seed_current(connection)
        )
        columns = """source, stable_id, raw_token, resolution_token, policy_version,
                      context_version, snapshot_id, listing_state, hiring_state,
                      identity_state, reason, explicit_domain, resolved_company_key,
                      key_derivation, company_id, occurred_at, bronze_fetched_at,
                      bronze_last_checked_at"""
        for field, value in (
            ("policy_version", "source-lifecycle-v0"),
            ("context_version", "yc-context-v0"),
        ):
            new_observation = connection.execute(
                f"""INSERT INTO silver.source_lifecycle_observation ({columns})
                    SELECT source, stable_id, raw_token, resolution_token,
                           CASE WHEN %s = 'policy_version' THEN %s ELSE policy_version END,
                           CASE WHEN %s = 'context_version' THEN %s ELSE context_version END,
                           snapshot_id, listing_state, hiring_state, identity_state,
                           reason, explicit_domain, resolved_company_key,
                           key_derivation, company_id, occurred_at, bronze_fetched_at,
                           bronze_last_checked_at
                    FROM silver.source_lifecycle_observation WHERE id = %s
                    RETURNING id""",
                (field, value, field, value, observation_id),
            ).fetchone()[0]
            connection.execute(
                "UPDATE silver.source_currentness SET current_observation_id = %s WHERE stable_id = %s",
                (new_observation, stable_id),
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                    (stable_id,),
                ).fetchone()[0]
                == 0
            )
        connection.execute(
            "UPDATE silver.source_currentness SET current_observation_id = %s WHERE stable_id = %s",
            (observation_id, stable_id),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM gold.current_source_evidence WHERE source_stable_id = %s",
                (stable_id,),
            ).fetchone()[0]
            == 1
        )


def test_snapshot_history_is_immutable_and_unknown_event_is_not_insertable(
    evidence_database_url: str,
):
    with psycopg.connect(evidence_database_url) as connection:
        stable_id, _domain, _gold, (observation_id, match_id, _company_id) = (
            _seed_current(
                connection, source="yc", hiring_state="unknown", occurred_at=None
            )
        )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE silver.source_context_snapshot SET normalized_text = 'edited' WHERE stable_id = %s",
                (stable_id,),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "DELETE FROM silver.source_context_snapshot WHERE stable_id = %s",
                (stable_id,),
            )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.match_source_evidence (match_id, observation_id, cutoff, as_of) VALUES (%s, %s, %s, %s)",
                (
                    match_id,
                    observation_id,
                    EVENT - timedelta(days=1),
                    EVENT + timedelta(days=1),
                ),
            )


def test_evidence_links_validate_window_and_preserve_match_identity(
    evidence_database_url: str,
):
    with psycopg.connect(evidence_database_url) as connection:
        _stable, _domain, _gold, (observation_id, match_id, company_id) = _seed_current(
            connection
        )
        cutoff = as_of = EVENT
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.match SET company_id = %s WHERE id = %s",
                (uuid4(), match_id),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.match SET user_id = %s WHERE id = %s",
                (uuid4(), match_id),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.match SET id = %s WHERE id = %s",
                (uuid4(), match_id),
            )
        connection.execute(
            "INSERT INTO operational.match_source_evidence (match_id, observation_id, cutoff, as_of) VALUES (%s, %s, %s, %s)",
            (match_id, observation_id, cutoff, as_of),
        )
        connection.execute(
            "UPDATE operational.match SET status = 'contacted', notes = 'kept' WHERE id = %s",
            (match_id,),
        )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.match SET company_id = %s WHERE id = %s",
                (uuid4(), match_id),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.match SET user_id = %s WHERE id = %s",
                (uuid4(), match_id),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.match SET id = %s WHERE id = %s",
                (uuid4(), match_id),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "DELETE FROM operational.match_source_evidence WHERE match_id = %s",
                (match_id,),
            )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.match_source_evidence (match_id, observation_id, cutoff, as_of) VALUES (%s, %s, %s, %s)",
                (match_id, uuid4(), cutoff, as_of),
            )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.match_source_evidence (match_id, observation_id, cutoff, as_of) VALUES (%s, %s, %s, %s)",
                (
                    match_id,
                    observation_id,
                    EVENT + timedelta(days=1),
                    EVENT + timedelta(days=2),
                ),
            )
        (
            _other_stable,
            _other_domain,
            _other_gold,
            (_other_observation, other_match, _other_company),
        ) = _seed_current(connection)
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.match_source_evidence (match_id, observation_id, cutoff, as_of) VALUES (%s, %s, %s, %s)",
                (other_match, observation_id, cutoff, as_of),
            )
        assert connection.execute(
            "SELECT company_id, status, notes FROM operational.match WHERE id = %s",
            (match_id,),
        ).fetchone() == (company_id, "contacted", "kept")


def test_linked_history_survives_a_current_pointer_transition(
    evidence_database_url: str,
):
    with psycopg.connect(evidence_database_url) as connection:
        stable_id, _domain, _gold, (observation_id, match_id, _company_id) = (
            _seed_current(connection)
        )
        connection.execute(
            "INSERT INTO operational.match_source_evidence (match_id, observation_id, cutoff, as_of) VALUES (%s, %s, %s, %s)",
            (match_id, observation_id, EVENT, EVENT),
        )
        replacement_id = connection.execute(
            """INSERT INTO silver.source_lifecycle_observation
               (source, stable_id, raw_token, resolution_token, policy_version,
                context_version, snapshot_id, listing_state, hiring_state,
                identity_state, reason, explicit_domain, resolved_company_key,
                key_derivation, company_id, occurred_at, bronze_fetched_at,
                bronze_last_checked_at)
               SELECT source, stable_id, raw_token, resolution_token, policy_version,
                      context_version, snapshot_id, listing_state, hiring_state,
                      identity_state, 'later observation', explicit_domain,
                      resolved_company_key, key_derivation, company_id, occurred_at,
                      bronze_fetched_at, bronze_last_checked_at
               FROM silver.source_lifecycle_observation WHERE id = %s RETURNING id""",
            (observation_id,),
        ).fetchone()[0]
        connection.execute(
            "UPDATE silver.source_currentness SET current_observation_id = %s WHERE stable_id = %s",
            (replacement_id, stable_id),
        )
        assert connection.execute(
            "SELECT observation_id FROM operational.match_source_evidence WHERE match_id = %s",
            (match_id,),
        ).fetchone() == (observation_id,)
        assert connection.execute(
            "SELECT observation_id FROM gold.current_source_evidence WHERE source_stable_id = %s",
            (stable_id,),
        ).fetchone() == (replacement_id,)


def test_evidence_requires_live_guarded_context_and_inclusive_nonnull_event(
    evidence_database_url: str,
):
    with psycopg.connect(evidence_database_url) as connection:
        _stable, _domain, _gold, (observation_id, match_id, _company_id) = (
            _seed_current(connection, occurred_at=None)
        )
        now = EVENT + timedelta(days=2)
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.match_source_evidence (match_id, observation_id, cutoff, as_of) VALUES (%s, %s, %s, %s)",
                (match_id, observation_id, EVENT - timedelta(days=1), now),
            )


def test_migration_rejects_deferred_unvalidated_history_foreign_key():
    with (
        provisioned_postgres("huginn_evidence_fk") as url,
        psycopg.connect(url, autocommit=True) as connection,
    ):
        connection.execute(
            "ALTER TABLE operational.match_source_evidence "
            "DROP CONSTRAINT match_source_evidence_observation_fkey"
        )
        connection.execute(
            """ALTER TABLE operational.match_source_evidence
               ADD CONSTRAINT match_source_evidence_observation_fkey
               FOREIGN KEY (observation_id)
               REFERENCES silver.source_lifecycle_observation (id)
               DEFERRABLE INITIALLY DEFERRED NOT VALID"""
        )
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="incompatible match source evidence foreign keys",
        ):
            connection.execute(MIGRATION.read_text())

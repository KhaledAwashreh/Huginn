"""PostgreSQL 16 coverage for matchmaking's additive schema changes.

Every scenario runs in its own database created inside the disposable server
from tests/postgres_harness.py. No developer database URL is used.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tests.postgres_harness import SCHEMA_DIR, SCHEMA_FILES

_ROOT = Path(__file__).resolve().parents[2]
_UNIQUE_MIGRATION = SCHEMA_DIR / "operational-match-user-company-unique.sql"
_SIGNAL_INDEX_MIGRATION = SCHEMA_DIR / "gold-company-signal-matchmaking-index.sql"
_UNIQUE_NAME = "match_user_company_unique"
_INDEX_NAME = "company_signal_company_occurred_at_idx"


def _url_for_dbname(database_url: str, dbname: str) -> str:
    info = conninfo_to_dict(database_url)
    info["dbname"] = dbname
    return make_conninfo(**info)


@contextlib.contextmanager
def _scratch_database(database_url: str) -> Iterator[str]:
    name = f"huginn_match_migration_{uuid.uuid4().hex[:10]}"
    admin_url = _url_for_dbname(database_url, "postgres")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    try:
        scratch_url = _url_for_dbname(database_url, name)
        with psycopg.connect(scratch_url, autocommit=True) as conn:
            for filename in SCHEMA_FILES:
                conn.execute((SCHEMA_DIR / filename).read_text())
        yield scratch_url
    finally:
        with (
            contextlib.suppress(Exception),
            psycopg.connect(admin_url, autocommit=True) as conn,
        ):
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@contextlib.contextmanager
def _legacy_match_schema(database_url: str) -> Iterator[str]:
    """Build the old Match shape from the fresh bootstrap in a scratch DB."""
    with (
        _scratch_database(database_url) as scratch_url,
        psycopg.connect(scratch_url, autocommit=True) as conn,
    ):
        conn.execute(
            "ALTER TABLE operational.match DROP CONSTRAINT match_user_company_unique"
        )
        yield scratch_url


def _insert_user_and_company(
    conn: psycopg.Connection,
    *,
    user_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = user_id or uuid.uuid4()
    company_id = company_id or uuid.uuid4()
    account_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO operational.accounts (id, username, password_hash) "
        "VALUES (%s, %s, 'hash')",
        (account_id, f"user-{user_id}"),
    )
    conn.execute(
        "INSERT INTO operational.users "
        "(id, account_id, first_name, last_name, email, phone_number, country_of_residence) "
        "VALUES (%s, %s, 'First', 'Last', %s, '1', 'US')",
        (user_id, account_id, f"{user_id}@example.test"),
    )
    conn.execute(
        "INSERT INTO gold.company (id, domain, name) VALUES (%s, %s, 'Company')",
        (company_id, f"{company_id}.example.test"),
    )
    return user_id, company_id


def _constraint_catalog(database_url: str) -> tuple:
    query = """
        SELECT ns.nspname, tbl.relname, c.conname, c.contype,
               c.condeferrable, c.condeferred, c.convalidated,
               ARRAY(SELECT a.attname
                     FROM unnest(c.conkey) WITH ORDINALITY AS key(attnum, ord)
                     JOIN pg_attribute AS a
                       ON a.attrelid = c.conrelid AND a.attnum = key.attnum
                     ORDER BY key.ord),
               idxns.nspname, idx.relname, i.indisunique, i.indisvalid,
               i.indisready, i.indislive, i.indimmediate,
               i.indnkeyatts, i.indnatts,
               ARRAY(SELECT a.attname
                     FROM unnest(i.indkey::smallint[]) WITH ORDINALITY AS key(attnum, ord)
                     JOIN pg_attribute AS a
                       ON a.attrelid = i.indrelid AND a.attnum = key.attnum
                     ORDER BY key.ord),
               i.indexprs IS NULL, i.indpred IS NULL, am.amname
        FROM pg_constraint AS c
        JOIN pg_class AS tbl ON tbl.oid = c.conrelid
        JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
        JOIN pg_class AS idx ON idx.oid = c.conindid
        JOIN pg_namespace AS idxns ON idxns.oid = idx.relnamespace
        JOIN pg_index AS i ON i.indexrelid = idx.oid
        JOIN pg_am AS am ON am.oid = idx.relam
        WHERE ns.nspname = 'operational' AND tbl.relname = 'match'
          AND c.conname = %s
    """
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(query, (_UNIQUE_NAME,)).fetchall()
    assert len(rows) == 1
    return rows[0]


@pytest.mark.parametrize(
    "status", ("new", "contacted", "responded", "dismissed", "converted")
)
def test_fresh_bootstrap_enforces_user_company_identity_across_statuses(
    integration_database_url: str, status: str
):
    with (
        _scratch_database(integration_database_url) as url,
        psycopg.connect(url) as conn,
    ):
        user_id, company_id = _insert_user_and_company(conn)
        other_user_id, _ = _insert_user_and_company(conn)
        conn.execute(
            "INSERT INTO operational.match (user_id, company_id, status) VALUES (%s,%s,%s)",
            (user_id, company_id, status),
        )
        conn.commit()
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(
                "INSERT INTO operational.match (user_id, company_id, status) VALUES (%s,%s,'new')",
                (user_id, company_id),
            )
        conn.rollback()
        conn.execute(
            "INSERT INTO operational.match (user_id, company_id, status) VALUES (%s,%s,'converted')",
            (other_user_id, company_id),
        )


def test_upgrade_adds_exact_named_constraint_and_is_repeatable(
    integration_database_url: str,
):
    with (
        _legacy_match_schema(integration_database_url) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        conn.execute(_UNIQUE_MIGRATION.read_text())
        first = _constraint_catalog(url)
        conn.execute(_UNIQUE_MIGRATION.read_text())
        assert _constraint_catalog(url) == first
        assert first[:7] == (
            "operational",
            "match",
            _UNIQUE_NAME,
            "u",
            False,
            False,
            True,
        )
        assert first[7:10] == (["user_id", "company_id"], "operational", _UNIQUE_NAME)
        assert first[10:17] == (True, True, True, True, True, 2, 2)
        assert first[17:21] == (["user_id", "company_id"], True, True, "btree")


def test_upgrade_renames_one_equivalent_constraint(
    integration_database_url: str,
):
    with (
        _legacy_match_schema(integration_database_url) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        conn.execute(
            "ALTER TABLE operational.match ADD CONSTRAINT old_match_pair "
            "UNIQUE (user_id, company_id)"
        )
        conn.execute(_UNIQUE_MIGRATION.read_text())
        assert _constraint_catalog(url)[2] == _UNIQUE_NAME


@pytest.mark.parametrize(
    "definition",
    [
        "UNIQUE (company_id, user_id)",
        "UNIQUE (user_id, company_id) DEFERRABLE INITIALLY DEFERRED",
    ],
)
def test_upgrade_rejects_incompatible_same_name_constraint(
    integration_database_url: str, definition: str
):
    with (
        _legacy_match_schema(integration_database_url) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        conn.execute(
            f"ALTER TABLE operational.match ADD CONSTRAINT {_UNIQUE_NAME} {definition}"
        )
        with pytest.raises(psycopg.Error, match="conflicting"):
            conn.execute(_UNIQUE_MIGRATION.read_text())


def test_upgrade_refuses_partial_canonical_name_index(
    integration_database_url: str,
):
    with (
        _legacy_match_schema(integration_database_url) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        conn.execute(
            "CREATE UNIQUE INDEX match_user_company_unique "
            "ON operational.match (user_id, company_id) WHERE status = 'new'"
        )
        with pytest.raises(psycopg.Error, match="occupied"):
            conn.execute(_UNIQUE_MIGRATION.read_text())


def test_upgrade_refuses_multiple_equivalent_constraints(
    integration_database_url: str,
):
    with (
        _legacy_match_schema(integration_database_url) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        conn.execute(
            "ALTER TABLE operational.match ADD CONSTRAINT pair_one "
            "UNIQUE (user_id, company_id)"
        )
        conn.execute(
            "ALTER TABLE operational.match ADD CONSTRAINT pair_two "
            "UNIQUE (user_id, company_id)"
        )
        with pytest.raises(psycopg.Error, match="equivalent"):
            conn.execute(_UNIQUE_MIGRATION.read_text())


def test_duplicate_preflight_preserves_matches_and_child_references(
    integration_database_url: str,
):
    with (
        _legacy_match_schema(integration_database_url) as url,
        psycopg.connect(url) as conn,
    ):
        user_id, company_id = _insert_user_and_company(conn)
        match_ids = [uuid.uuid4(), uuid.uuid4()]
        conn.cursor().executemany(
            "INSERT INTO operational.match (id, user_id, company_id) "
            "VALUES (%s, %s, %s)",
            [(match_id, user_id, company_id) for match_id in match_ids],
        )
        conn.execute(
            "INSERT INTO operational.match_feedback (match_id, rating) "
            "VALUES (%s, 'positive')",
            (match_ids[0],),
        )
        conn.execute(
            "INSERT INTO operational.communication (match_id, channel) "
            "VALUES (%s, 'email')",
            (match_ids[1],),
        )
        conn.commit()

        with psycopg.connect(
            url,
            autocommit=True,
            options="-c lock_timeout=5000 -c statement_timeout=10000",
        ) as conn:
            with pytest.raises(
                psycopg.errors.UniqueViolation, match="duplicate"
            ) as exc:
                conn.execute(_UNIQUE_MIGRATION.read_text())
            assert str(match_ids[0]) in str(exc.value)
            assert str(match_ids[1]) in str(exc.value)

        with psycopg.connect(url) as conn:
            assert conn.execute(
                "SELECT id FROM operational.match ORDER BY id"
            ).fetchall() == [(match_id,) for match_id in sorted(match_ids)]
            assert conn.execute(
                "SELECT match_id FROM operational.match_feedback"
            ).fetchall() == [(match_ids[0],)]
            assert conn.execute(
                "SELECT match_id FROM operational.communication"
            ).fetchall() == [(match_ids[1],)]


def test_gold_signal_index_is_canonical_and_upgrade_is_repeatable(
    integration_database_url: str,
):
    with (
        _scratch_database(integration_database_url) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        conn.execute("DROP INDEX gold.company_signal_company_occurred_at_idx")
        conn.execute(_SIGNAL_INDEX_MIGRATION.read_text())
        first = conn.execute(
            "SELECT ns.nspname, tbl.relname, idx.relname, am.amname, "
            "i.indisunique, i.indisvalid, i.indisready, i.indislive, "
            "i.indnkeyatts, i.indnatts, i.indpred IS NULL, i.indexprs IS NULL, "
            "ARRAY(SELECT a.attname FROM unnest(i.indkey::smallint[]) "
            "WITH ORDINALITY AS k(attnum, ord) JOIN pg_attribute a "
            "ON a.attrelid=i.indrelid AND a.attnum=k.attnum ORDER BY k.ord) "
            "FROM pg_index i JOIN pg_class idx ON idx.oid=i.indexrelid "
            "JOIN pg_namespace ns ON ns.oid=idx.relnamespace "
            "JOIN pg_class tbl ON tbl.oid=i.indrelid "
            "JOIN pg_am am ON am.oid=idx.relam "
            "WHERE ns.nspname='gold' AND idx.relname=%s",
            (_INDEX_NAME,),
        ).fetchone()
        conn.execute(_SIGNAL_INDEX_MIGRATION.read_text())
        second = conn.execute(
            "SELECT pg_get_indexdef(indexrelid) FROM pg_index "
            "JOIN pg_class ON pg_class.oid=pg_index.indexrelid "
            "JOIN pg_namespace ON pg_namespace.oid=pg_class.relnamespace "
            "WHERE nspname='gold' AND relname=%s",
            (_INDEX_NAME,),
        ).fetchone()
        assert first == (
            "gold",
            "company_signal",
            _INDEX_NAME,
            "btree",
            False,
            True,
            True,
            True,
            2,
            2,
            True,
            True,
            ["company_id", "occurred_at"],
        )
        assert second is not None


@pytest.mark.parametrize(
    "definition",
    (
        "CREATE TABLE gold.company_signal_company_occurred_at_idx (id int)",
        "CREATE INDEX company_signal_company_occurred_at_idx ON gold.company_signal (occurred_at, company_id)",
        "CREATE INDEX company_signal_company_occurred_at_idx ON gold.company_signal (company_id, occurred_at DESC)",
        "CREATE INDEX company_signal_company_occurred_at_idx ON gold.company_signal (company_id, occurred_at) WHERE source='x'",
    ),
)
def test_signal_index_conflicts_rejected(integration_database_url, definition):
    with (
        _scratch_database(integration_database_url) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        conn.execute("DROP INDEX gold.company_signal_company_occurred_at_idx")
        conn.execute(definition)
        with pytest.raises(psycopg.Error, match="incompatible"):
            conn.execute(_SIGNAL_INDEX_MIGRATION.read_text())


def test_unique_migration_obtains_write_blocking_lock_before_audit(
    integration_database_url,
):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    with (
        _legacy_match_schema(integration_database_url) as url,
        psycopg.connect(url) as blocker,
    ):
        table_oid = blocker.execute(
            "SELECT 'operational.match'::regclass::oid"
        ).fetchone()[0]
        blocker.execute("LOCK TABLE operational.match IN ROW EXCLUSIVE MODE")
        started = threading.Event()

        def migrate():
            with psycopg.connect(
                url,
                autocommit=True,
                options="-c lock_timeout=5000 -c statement_timeout=6000",
            ) as conn:
                started.set()
                conn.execute(_UNIQUE_MIGRATION.read_text())

        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(migrate)
            try:
                assert started.wait(3)
                with psycopg.connect(
                    url, autocommit=True, options="-c statement_timeout=1000"
                ) as observer:
                    waiting = False
                    for _ in range(50):
                        waiting = observer.execute(
                            "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE relation=%s AND mode='AccessExclusiveLock' AND NOT granted)",
                            (table_oid,),
                        ).fetchone()[0]
                        if waiting:
                            break
                        time.sleep(0.02)
                    assert waiting
            finally:
                blocker.rollback()
            result.result(timeout=7)


def test_canonical_plus_equivalent_requires_reconciliation(integration_database_url):
    with (
        _scratch_database(integration_database_url) as url,
        psycopg.connect(url, autocommit=True) as conn,
    ):
        conn.execute(
            "ALTER TABLE operational.match ADD CONSTRAINT pair_extra UNIQUE(user_id,company_id)"
        )
        with pytest.raises(psycopg.Error, match="equivalent"):
            conn.execute(_UNIQUE_MIGRATION.read_text())

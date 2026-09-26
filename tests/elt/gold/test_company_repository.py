import pytest

from huginn.elt.gold.repositories import company_repository
from huginn.elt.gold.repositories.company_repository import (
    PostgresCompanyRepository,
    build_read_unenriched_company_names_query,
    build_upsert_query,
)


def test_build_upsert_query_includes_only_columns_present_in_new_values():
    """A write carrying a `name` takes the upsert shape, since that is the
    one caller shape that can insert: one statement, a new domain inserted
    and an existing one updated in place, with no read in front of it. Only
    the columns `new_values` supplies are bound.
    """
    sql, params = build_upsert_query(
        "acme.com", {"name": "Acme"}, bump_current_since=False
    )

    assert "acme.com" not in sql
    assert "Acme" not in sql
    assert params == ("acme.com", "Acme")
    assert "INSERT INTO gold.company (domain, name)" in sql
    assert "ON CONFLICT (domain) DO UPDATE" in sql
    assert "business_sector" not in sql


def test_build_upsert_query_updates_only_when_new_values_omits_name():
    """The other shape, and the one `name` decides. Regression, ADR-0013: a
    Type-2-only write used to build an INSERT with no `name` in its column
    list, and because Postgres validates NOT NULL before ON CONFLICT is
    considered, that failed with NotNullViolation even when the row existed
    and only the update branch should have run. There is no name to insert,
    so the write must not attempt an insert at all.
    """
    sql, params = build_upsert_query(
        "acme.com", {"business_sector": ["fintech"]}, bump_current_since=True
    )

    assert "INSERT" not in sql
    assert "ON CONFLICT" not in sql
    assert sql.startswith("UPDATE gold.company SET business_sector = %s")
    assert "current_since = now()" in sql
    assert params == (["fintech"], "acme.com")


def test_build_upsert_query_never_takes_the_domain_from_new_values():
    """Holds for both shapes, not just the upsert one: `domain` is the
    ON CONFLICT target and the WHERE key, and it always comes from the
    explicit parameter, so no caller string reaches either.
    """
    upsert_sql, upsert_params = build_upsert_query(
        "acme.com", {"name": "Acme", "domain": "attacker.example"}, False
    )
    update_sql, update_params = build_upsert_query(
        "acme.com", {"domain": "attacker.example"}, False
    )

    for sql, params in ((upsert_sql, upsert_params), (update_sql, update_params)):
        assert "acme.com" not in sql
        assert "attacker.example" not in sql
        assert "attacker.example" not in params
        assert params.count("acme.com") == 1


def test_build_upsert_query_keeps_a_none_valued_name_on_the_insert_branch():
    """Key presence, not truthiness, picks the shape. A caller that writes
    `{"name": None}` has asked to null a NOT NULL column, and the database
    saying so is the answer; degrading the write to an update would hide
    the mistake behind a silent success.
    """
    sql, params = build_upsert_query(
        "acme.com", {"name": None, "company_status": "Active"}, False
    )

    assert "INSERT INTO gold.company (domain, name, company_status)" in sql
    assert params == ("acme.com", None, "Active")


def test_build_upsert_query_drops_an_unrecognized_key_rather_than_interpolating_it():
    sql, params = build_upsert_query(
        "acme.com", {"name": "Acme", "not_a_real_column": "x"}, bump_current_since=False
    )

    assert "not_a_real_column" not in sql
    assert "x" not in params


def test_build_upsert_query_bumps_current_since_only_when_asked():
    sql_no_bump, _ = build_upsert_query(
        "acme.com", {"name": "Acme"}, bump_current_since=False
    )
    sql_bump, _ = build_upsert_query(
        "acme.com", {"name": "Acme"}, bump_current_since=True
    )

    assert "current_since" not in sql_no_bump
    assert "current_since = now()" in sql_bump


def test_build_upsert_query_always_bumps_updated_at():
    sql, _ = build_upsert_query("acme.com", {"name": "Acme"}, bump_current_since=False)

    assert "updated_at = now()" in sql


def test_build_upsert_query_is_an_on_conflict_upsert_targeting_domain():
    sql, _ = build_upsert_query("acme.com", {"name": "Acme"}, bump_current_since=False)

    assert "ON CONFLICT (domain)" in sql
    assert "INSERT INTO gold.company" in sql


def test_build_read_unenriched_company_names_query_binds_limit_as_a_parameter():
    """The candidate query binds its limit and selects unenriched names."""
    sql, params = build_read_unenriched_company_names_query(50)

    assert params == (50,)
    assert "50" not in sql
    assert "gold.company" in sql
    assert "business_sector IS NULL" in sql
    assert "DISTINCT ON (name)" in sql
    assert "ORDER BY created_at, id" in sql
    assert "LIMIT %s" in sql


def test_build_read_company_names_pending_eu_startups_search_query_binds_limit_as_a_parameter():
    """The candidate query binds its limit and selects companies pending
    EU-Startups search.
    """
    from huginn.elt.gold.repositories.company_repository import (
        build_read_company_names_pending_eu_startups_search_query,
    )

    sql, params = build_read_company_names_pending_eu_startups_search_query(50)

    assert params == (50,)
    assert "50" not in sql
    assert "gold.company" in sql
    assert "eu_startups_searched_at IS NULL" in sql
    assert "LIMIT %s" in sql


class _FakeConnectionThatFailsToOpenACursor:
    def __init__(self):
        self.closed = False

    def cursor(self):
        raise RuntimeError("simulated cursor-open failure")

    def close(self):
        self.closed = True


def test_enter_closes_the_connection_when_opening_the_cursor_fails(monkeypatch):
    """Regression, same bug class as commit 351ab90 (Silver's
    PostgresConnectionScope): if __enter__ opened the connection but
    cursor() then raises, __exit__ never runs (the `with` protocol skips
    it when __enter__ itself raises), so the connection must be closed
    here or it leaks.
    """
    fake_conn = _FakeConnectionThatFailsToOpenACursor()
    monkeypatch.setattr(
        company_repository.psycopg, "connect", lambda database_url: fake_conn
    )
    repository = PostgresCompanyRepository("postgresql://example.invalid/huginn")

    with pytest.raises(RuntimeError, match="simulated cursor-open failure"):
        repository.__enter__()

    assert fake_conn.closed is True

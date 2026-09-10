import pytest

from huginn.elt.gold.repositories import company_repository
from huginn.elt.gold.repositories.company_repository import (
    PostgresCompanyRepository,
    build_upsert_query,
)


def test_build_upsert_query_includes_only_columns_present_in_new_values():
    sql, params = build_upsert_query(
        "acme.com", {"name": "Acme"}, bump_current_since=False
    )

    assert "acme.com" not in sql
    assert "Acme" not in sql
    assert params == ("acme.com", "Acme")
    assert "domain" in sql
    assert "name" in sql
    assert "business_sector" not in sql


def test_build_upsert_query_always_includes_domain_even_when_new_values_omits_it():
    """Regression: domain is a NOT NULL ON CONFLICT target. It must come
    from the explicit `domain` parameter, not from a "domain" key inside
    new_values — a caller (e.g. a Type-2-only update) may reasonably omit
    it there. Omitting it from the generated INSERT would make Postgres
    reject the statement on the NOT NULL constraint before ON CONFLICT is
    even considered, even when only the UPDATE branch should run.
    """
    sql, params = build_upsert_query(
        "acme.com", {"icp_filter_pass": True}, bump_current_since=True
    )

    assert params[0] == "acme.com"
    assert "INSERT INTO gold.company (domain, icp_filter_pass)" in sql


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

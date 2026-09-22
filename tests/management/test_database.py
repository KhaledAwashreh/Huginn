import logging

import psycopg
import pytest

from huginn.management import database

DATABASE_URL = "postgresql://manager:secret@management.test/huginn"
EXPECTED_PROBES = (
    "SELECT 1",
    "SELECT id, username, password_hash, status, created_at, updated_at "
    "FROM operational.accounts LIMIT 0",
    "SELECT id, account_id, first_name, last_name, email, phone_number, "
    "country_of_residence, timezone, created_at, updated_at "
    "FROM operational.users LIMIT 0",
    "SELECT id, user_id, headline, professional_summary, skills, experience, "
    "previous_projects, created_at, updated_at "
    "FROM operational.professional_profiles LIMIT 0",
)


class FakeConnection:
    def __init__(self, error=None):
        self.error = error
        self.queries = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.closed = True

    def execute(self, query):
        self.queries.append(query)
        if self.error is not None:
            raise self.error


def test_constructor_does_not_connect(monkeypatch):
    def unexpected_connect(*args, **kwargs):
        pytest.fail("constructor connected to Postgres")

    monkeypatch.setattr(database.psycopg, "connect", unexpected_connect)

    database.PostgresReadiness(DATABASE_URL)


def test_is_ready_uses_read_only_timeouts_and_exact_probes(monkeypatch):
    connection = FakeConnection()
    connect_calls = []

    def fake_connect(*args, **kwargs):
        connect_calls.append((args, kwargs))
        return connection

    monkeypatch.setattr(database.psycopg, "connect", fake_connect)

    assert database.PostgresReadiness(DATABASE_URL).is_ready() is True
    assert connect_calls == [
        (
            (DATABASE_URL,),
            {
                "connect_timeout": 2,
                "options": (
                    "-c statement_timeout=2000 -c default_transaction_read_only=on"
                ),
            },
        )
    ]
    assert connection.queries == list(EXPECTED_PROBES)
    assert connection.closed is True


@pytest.mark.parametrize("failure_at", ("connect", "query"))
def test_psycopg_failure_returns_false_and_logs_safely(
    monkeypatch,
    caplog,
    failure_at,
):
    exception_text = f"could not connect to {DATABASE_URL}"
    error = psycopg.OperationalError(exception_text)
    connection = FakeConnection(error if failure_at == "query" else None)

    def fake_connect(*args, **kwargs):
        if failure_at == "connect":
            raise error
        return connection

    monkeypatch.setattr(database.psycopg, "connect", fake_connect)

    with caplog.at_level(logging.WARNING, logger=database.__name__):
        result = database.PostgresReadiness(DATABASE_URL).is_ready()

    assert result is False
    assert len(caplog.records) == 1
    assert caplog.records[0].message == (
        "Management readiness failed: OperationalError"
    )
    assert exception_text not in caplog.text
    assert DATABASE_URL not in caplog.text
    assert "secret" not in caplog.text
    assert connection.closed is (failure_at == "query")


def test_programming_error_propagates_and_closes_connection(monkeypatch):
    error = TypeError("deliberate programming error")
    connection = FakeConnection(error)
    monkeypatch.setattr(database.psycopg, "connect", lambda *args, **kwargs: connection)

    with pytest.raises(TypeError, match="deliberate programming error"):
        database.PostgresReadiness(DATABASE_URL).is_ready()

    assert connection.closed is True

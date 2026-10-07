from types import SimpleNamespace

import psycopg
import pytest

from huginn.management.persistence.contracts.database import JsonParameter
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.errors.database import DatabaseError, IntegrityError


class Cursor:
    def __init__(self, error=None, close_error=None):
        self.error = error
        self.close_error = close_error
        self.closed = False

    def execute(self, query, params):
        self.query, self.params = query, params
        if self.error:
            raise self.error

    def fetchone(self):
        return (1,)

    def fetchall(self):
        return [(1,)]

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error


def test_json_adaptation_and_implicit_result_cursor_cleanup():
    cursor = Cursor()
    session = PsycopgDatabaseSession(SimpleNamespace(cursor=lambda: cursor))
    assert session.execute(
        "SELECT %s", (JsonParameter([{"name": "skill"}]),)
    ).fetchone() == (1,)
    assert cursor.params[0].obj == [{"name": "skill"}]
    assert cursor.closed


def test_explicit_cursor_cleanup_on_body_failure():
    cursor = Cursor()
    session = PsycopgDatabaseSession(SimpleNamespace(cursor=lambda: cursor))
    with pytest.raises(ValueError), session.cursor():
        raise ValueError("body")
    assert cursor.closed


@pytest.mark.parametrize(
    "error,error_type",
    [
        (psycopg.errors.UniqueViolation("password-sentinel"), IntegrityError),
        (psycopg.OperationalError("password-sentinel"), DatabaseError),
    ],
)
def test_driver_failures_translate_to_safe_metadata_and_close_cursor(error, error_type):
    cursor = Cursor(error)
    session = PsycopgDatabaseSession(SimpleNamespace(cursor=lambda: cursor))
    with pytest.raises(error_type) as failure:
        session.execute("SELECT 1")
    assert failure.value.error_name == type(error).__name__
    assert failure.value.sqlstate == error.sqlstate
    assert "password-sentinel" not in str(failure.value)
    assert failure.value.__cause__ is None
    assert cursor.closed


def test_failed_row_fetch_closes_implicit_cursor():
    cursor = Cursor()

    def fail():
        raise psycopg.OperationalError("token-sentinel")

    cursor.fetchone = fail
    session = PsycopgDatabaseSession(SimpleNamespace(cursor=lambda: cursor))
    with pytest.raises(DatabaseError):
        session.execute("SELECT 1").fetchone()
    assert cursor.closed


def test_execute_error_is_not_replaced_by_cursor_close_error():
    cursor = Cursor(
        psycopg.errors.UniqueViolation("execute-sentinel"),
        psycopg.OperationalError("close-sentinel"),
    )
    session = PsycopgDatabaseSession(SimpleNamespace(cursor=lambda: cursor))

    with pytest.raises(IntegrityError) as failure:
        session.execute("SELECT 1")

    assert failure.value.error_name == "UniqueViolation"
    assert cursor.closed


def test_explicit_cursor_execute_error_is_not_replaced_by_close_error():
    cursor = Cursor(
        psycopg.errors.UniqueViolation("execute-sentinel"),
        psycopg.OperationalError("close-sentinel"),
    )
    session = PsycopgDatabaseSession(SimpleNamespace(cursor=lambda: cursor))

    with pytest.raises(IntegrityError) as failure, session.cursor() as db_cursor:
        db_cursor.execute("SELECT 1")

    assert failure.value.error_name == "UniqueViolation"
    assert cursor.closed


def test_fetch_error_is_not_replaced_by_cursor_close_error():
    cursor = Cursor(close_error=psycopg.errors.UniqueViolation("close-sentinel"))

    def fail():
        raise psycopg.OperationalError("fetch-sentinel")

    cursor.fetchone = fail
    session = PsycopgDatabaseSession(SimpleNamespace(cursor=lambda: cursor))

    with pytest.raises(DatabaseError) as failure:
        session.execute("SELECT 1").fetchone()

    assert failure.value.error_name == "OperationalError"
    assert cursor.closed


def test_cursor_close_error_propagates_after_successful_fetch():
    cursor = Cursor(close_error=psycopg.OperationalError("close-sentinel"))
    session = PsycopgDatabaseSession(SimpleNamespace(cursor=lambda: cursor))

    with pytest.raises(DatabaseError) as failure:
        session.execute("SELECT 1").fetchone()

    assert failure.value.error_name == "OperationalError"
    assert cursor.closed

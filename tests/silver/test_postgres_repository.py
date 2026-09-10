from __future__ import annotations

import pytest

from huginn.silver import postgres_repository
from huginn.silver.postgres_repository import PostgresConnectionScope


class _FakeConnectionThatFailsToOpenACursor:
    def __init__(self):
        self.closed = False

    def cursor(self):
        raise RuntimeError("simulated cursor-open failure")

    def close(self):
        self.closed = True


def test_enter_closes_the_connection_when_opening_the_cursor_fails(monkeypatch):
    fake_conn = _FakeConnectionThatFailsToOpenACursor()
    monkeypatch.setattr(
        postgres_repository.psycopg, "connect", lambda database_url: fake_conn
    )
    scope = PostgresConnectionScope("postgresql://example.invalid/huginn")

    with pytest.raises(RuntimeError, match="simulated cursor-open failure"):
        scope.__enter__()

    assert fake_conn.closed is True

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


class _FakeCursorThatFailsToClose:
    def close(self):
        raise RuntimeError("simulated cursor-close failure")


class _FakeConnectionWithAFailingCursorClose:
    def __init__(self):
        self.cursor_obj = _FakeCursorThatFailsToClose()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_exit_still_rolls_back_and_does_not_mask_the_original_exception_when_cursor_close_fails(
    monkeypatch,
):
    fake_conn = _FakeConnectionWithAFailingCursorClose()
    monkeypatch.setattr(
        postgres_repository.psycopg, "connect", lambda database_url: fake_conn
    )
    scope = PostgresConnectionScope("postgresql://example.invalid/huginn")

    with pytest.raises(KeyError, match="original failure"), scope:
        raise KeyError("original failure")

    assert fake_conn.rolled_back is True
    assert fake_conn.committed is False
    assert fake_conn.closed is True


def test_exit_still_commits_when_cursor_close_fails_on_a_clean_exit(monkeypatch):
    fake_conn = _FakeConnectionWithAFailingCursorClose()
    monkeypatch.setattr(
        postgres_repository.psycopg, "connect", lambda database_url: fake_conn
    )
    scope = PostgresConnectionScope("postgresql://example.invalid/huginn")

    with scope:
        pass

    assert fake_conn.committed is True
    assert fake_conn.rolled_back is False
    assert fake_conn.closed is True

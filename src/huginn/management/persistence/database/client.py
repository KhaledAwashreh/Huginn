"""Management database adapters defined by ADR-0011."""

import logging
from collections.abc import Callable
from contextlib import suppress
from types import TracebackType
from typing import Any, Self

import psycopg
from psycopg.types.json import Jsonb

from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
    Parameters,
    Row,
)
from huginn.management.persistence.database.policy import (
    DATABASE_CONNECT_TIMEOUT_SECONDS,
    DATABASE_READINESS_TIMEOUT_SECONDS,
    MANAGEMENT_SCHEMA,
)
from huginn.management.persistence.errors.database import DatabaseError, IntegrityError

logger = logging.getLogger(__name__)

_PROBES = (
    "SELECT 1",
    "SELECT id, username, password_hash, status, created_at, updated_at "
    f"FROM {MANAGEMENT_SCHEMA}.accounts LIMIT 0",
    "SELECT id, account_id, first_name, last_name, email, phone_number, "
    "country_of_residence, timezone, created_at, updated_at "
    f"FROM {MANAGEMENT_SCHEMA}.users LIMIT 0",
    "SELECT id, user_id, headline, professional_summary, skills, experience, "
    "previous_projects, created_at, updated_at "
    f"FROM {MANAGEMENT_SCHEMA}.professional_profiles LIMIT 0",
    "SELECT id, account_id, token_digest, csrf_digest, created_at, expires_at, "
    f"revoked_at FROM {MANAGEMENT_SCHEMA}.sessions LIMIT 0",
    "SELECT id, user_id, name, description, created_at, updated_at "
    f"FROM {MANAGEMENT_SCHEMA}.service_offerings LIMIT 0",
    "SELECT id, user_id, name, industries, company_sizes, geographies, "
    "exclusions, created_at, updated_at "
    f"FROM {MANAGEMENT_SCHEMA}.ideal_client_profiles LIMIT 0",
    "SELECT id, user_id, name, service_offering_id, ideal_client_profile_id, "
    "is_active, created_at, updated_at "
    f"FROM {MANAGEMENT_SCHEMA}.client_discovery_strategies LIMIT 0",
)


class PostgresReadiness:
    """Read-only Postgres readiness adapter defined by ADR-0011."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def is_ready(self) -> bool:
        try:
            with psycopg.connect(
                self._database_url,
                connect_timeout=DATABASE_READINESS_TIMEOUT_SECONDS,
                options=(
                    f"-c statement_timeout={DATABASE_READINESS_TIMEOUT_SECONDS * 1000} "
                    "-c default_transaction_read_only=on"
                ),
            ) as conn:
                for query in _PROBES:
                    conn.execute(query)
            return True
        except psycopg.Error as exc:
            logger.warning("Management readiness failed: %s", type(exc).__name__)
            return False


class ManagementConnectionFactory:
    """Create management-owned PostgreSQL connections on demand."""

    def __init__(
        self,
        database_url: str,
        *,
        connector: Callable[..., psycopg.Connection] | None = None,
        connect_timeout: int = DATABASE_CONNECT_TIMEOUT_SECONDS,
    ) -> None:
        self._database_url = database_url
        self._connector = connector or psycopg.connect
        self._connect_timeout = connect_timeout

    def connect(self) -> DatabaseSession:
        return PsycopgDatabaseSession(
            _call(
                self._connector,
                self._database_url,
                connect_timeout=self._connect_timeout,
            )
        )


def _call(operation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Contain driver failure text; retain only structured metadata."""
    try:
        return operation(*args, **kwargs)
    except psycopg.Error as error:
        error_type = (
            IntegrityError
            if isinstance(error, psycopg.IntegrityError)
            else DatabaseError
        )
        raise error_type(
            sqlstate=error.sqlstate,
            constraint_name=getattr(error.diag, "constraint_name", None),
            error_name=type(error).__name__,
        ) from None


def _close_preserving_active_error(cursor: Any) -> None:
    """Close a cursor without replacing the error already being raised."""
    with suppress(BaseException):
        _call(cursor.close)


class _Cursor:
    def __init__(self, cursor: Any, *, close_after_fetch: bool = False) -> None:
        self._cursor = cursor
        self._close_after_fetch = close_after_fetch

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if exc_value is None:
            _call(self._cursor.close)
        else:
            _close_preserving_active_error(self._cursor)
        return False

    def execute(self, query: str, params: Parameters = ()) -> None:
        adapted = tuple(
            Jsonb(value.value) if isinstance(value, JsonParameter) else value
            for value in params
        )
        _call(self._cursor.execute, query, adapted)

    def fetchone(self) -> Row | None:
        try:
            row = _call(self._cursor.fetchone)
        except BaseException:
            if self._close_after_fetch:
                _close_preserving_active_error(self._cursor)
            raise
        if self._close_after_fetch:
            _call(self._cursor.close)
        return row

    def fetchall(self) -> list[Row]:
        try:
            rows = _call(self._cursor.fetchall)
        except BaseException:
            if self._close_after_fetch:
                _close_preserving_active_error(self._cursor)
            raise
        if self._close_after_fetch:
            _call(self._cursor.close)
        return rows


class PsycopgDatabaseSession:
    """Adapt a driver connection to the persistence-owned session contract."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def cursor(self) -> _Cursor:
        return _Cursor(_call(self._connection.cursor))

    def execute(self, query: str, params: Parameters = ()) -> _Cursor:
        cursor = _Cursor(_call(self._connection.cursor), close_after_fetch=True)
        try:
            cursor.execute(query, params)
        except BaseException:
            _close_preserving_active_error(cursor._cursor)
            raise
        return cursor

    def commit(self) -> None:
        _call(self._connection.commit)

    def rollback(self) -> None:
        _call(self._connection.rollback)

    def close(self) -> None:
        _call(self._connection.close)

"""Management database adapters defined by ADR-0011."""

import logging
from collections.abc import Callable
from types import TracebackType
from typing import Self

import psycopg

from huginn.management.constants.database import (
    DATABASE_CONNECT_TIMEOUT_SECONDS,
    DATABASE_READINESS_TIMEOUT_SECONDS,
    MANAGEMENT_SCHEMA,
)

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

    def connect(self) -> psycopg.Connection:
        return self._connector(
            self._database_url, connect_timeout=self._connect_timeout
        )


class UnitOfWork:
    """One explicit transaction and connection for an application operation."""

    def __init__(self, connection_factory: ManagementConnectionFactory) -> None:
        self._connection_factory = connection_factory
        self.connection: psycopg.Connection | None = None
        self._finished = False

    def __enter__(self) -> Self:
        self.connection = self._connection_factory.connect()
        self._finished = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        connection = self._require_connection()
        try:
            if not self._finished:
                self.rollback()
        finally:
            connection.close()
            self.connection = None
        return False

    def commit(self) -> None:
        connection = self._require_connection()
        if self._finished:
            raise RuntimeError("unit of work is already finished")
        try:
            connection.commit()
        except BaseException:
            connection.rollback()
            self._finished = True
            raise
        self._finished = True

    def rollback(self) -> None:
        connection = self._require_connection()
        if self._finished:
            raise RuntimeError("unit of work is already finished")
        connection.rollback()
        self._finished = True

    def _require_connection(self) -> psycopg.Connection:
        if self.connection is None:
            raise RuntimeError("unit of work is not active")
        return self.connection

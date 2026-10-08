"""Shared PostgreSQL persistence helpers for identity resources."""

from typing import Any

from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.errors.database import IntegrityError


class PostgresIdentityRepository:
    """Base for identity repositories bound to one unit-of-work connection."""

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def _one(self, query: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def _write(self, query: str, params: tuple[Any, ...]) -> tuple[Any, ...]:
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        assert row is not None
        return row

    @staticmethod
    def _translate(exc: IntegrityError) -> Exception:
        constraint = exc.constraint_name or ""
        if constraint == "accounts_username_lower_key":
            return ConflictError("username is already in use")
        if constraint in {
            "users_email_lower_key",
            "account_recovery_identity_email_lower_key",
        }:
            return ConflictError("email is already in use")
        return ValidationDomainError("identity data violates a database constraint")

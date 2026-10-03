"""Shared PostgreSQL persistence helpers for identity resources."""

from typing import Any

import psycopg

from huginn.management.errors.domain import ConflictError, ValidationDomainError


class PostgresIdentityRepository:
    """Base for identity repositories bound to one unit-of-work connection."""

    def __init__(self, connection: Any) -> None:
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
    def _translate(exc: psycopg.IntegrityError) -> Exception:
        constraint = getattr(getattr(exc, "diag", None), "constraint_name", "") or ""
        if constraint == "accounts_username_lower_key":
            return ConflictError("username is already in use")
        return ValidationDomainError("identity data violates a database constraint")

"""PostgreSQL persistence for owner-scoped service offerings."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.service_offering import ServiceOffering
from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.domain.value_objects.common import Page
from huginn.management.domain.value_objects.service_offering import (
    NewServiceOffering,
    ServiceOfferingChanges,
)
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.repositories.service_offering import (
    ServiceOfferingRepository,
)
from huginn.management.persistence.errors.database import IntegrityError


class PostgresServiceOfferingRepository(ServiceOfferingRepository):
    """Offering SQL bound to the caller's unit-of-work connection."""

    _columns = "id, user_id, name, description, created_at, updated_at"
    _update_columns = {"name": "name", "description": "description"}

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> ServiceOffering:
        return ServiceOffering(*row)

    def _one(self, query: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def create(self, offering: NewServiceOffering) -> ServiceOffering:
        row = self._one(
            f"INSERT INTO operational.service_offerings (user_id, name, description) "
            f"VALUES (%s, %s, %s) RETURNING {self._columns}",
            (offering.user_id, offering.name, offering.description),
        )
        assert row is not None
        return self._map(row)

    def get_owned(self, user_id: UUID, offering_id: UUID) -> ServiceOffering | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.service_offerings "
            "WHERE user_id = %s AND id = %s",
            (user_id, offering_id),
        )
        return self._map(row) if row else None

    def list_owned(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> Page[ServiceOffering]:
        rows = self.connection.execute(
            f"SELECT {self._columns} FROM operational.service_offerings "
            "WHERE user_id = %s ORDER BY created_at, id LIMIT %s OFFSET %s",
            (user_id, limit + 1, offset),
        ).fetchall()
        has_more = len(rows) > limit
        items = tuple(self._map(row) for row in rows[:limit])
        return Page(items, offset, limit, has_more)

    def update_owned(
        self, user_id: UUID, offering_id: UUID, changes: ServiceOfferingChanges
    ) -> ServiceOffering | None:
        supplied = changes.supplied_fields
        if not supplied:
            return self.get_owned(user_id, offering_id)
        if not supplied <= self._update_columns.keys():
            raise ValueError("unsupported offering update field")
        assignments = ", ".join(
            f"{self._update_columns[field]} = %s" for field in sorted(supplied)
        )
        params = tuple(changes.values[field] for field in sorted(supplied))
        row = self._one(
            f"UPDATE operational.service_offerings SET {assignments}, updated_at = clock_timestamp() "
            f"WHERE user_id = %s AND id = %s RETURNING {self._columns}",
            (*params, user_id, offering_id),
        )
        return self._map(row) if row else None

    def delete_owned(self, user_id: UUID, offering_id: UUID) -> bool:
        try:
            row = self._one(
                "DELETE FROM operational.service_offerings WHERE user_id = %s AND id = %s "
                "RETURNING id",
                (user_id, offering_id),
            )
        except IntegrityError as exc:
            if getattr(exc, "sqlstate", None) == "23503":
                raise ConflictError("offering is referenced") from exc
            raise ValidationDomainError(
                "offering violates a database constraint"
            ) from exc
        return row is not None

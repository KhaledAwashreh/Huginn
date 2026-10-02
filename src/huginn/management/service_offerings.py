"""Owned ServiceOffering persistence and application operations."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

import psycopg

from huginn.management.domain import (
    ConflictError,
    NewServiceOffering,
    NotFoundError,
    Page,
    Principal,
    ServiceOffering,
    ServiceOfferingChanges,
    ValidationDomainError,
)
from huginn.management.pagination import empty_page
from huginn.management.schemas import OfferingCreate, OfferingPatch, OfferingRead


class PostgresServiceOfferingRepository:
    """Offering SQL bound to the caller's unit-of-work connection."""

    _columns = "id, user_id, name, description, created_at, updated_at"
    _update_columns = {"name": "name", "description": "description"}

    def __init__(self, connection: Any) -> None:
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
        except psycopg.IntegrityError as exc:
            if getattr(exc, "sqlstate", None) == "23503":
                raise ConflictError("offering is referenced") from exc
            raise ValidationDomainError(
                "offering violates a database constraint"
            ) from exc
        return row is not None


class ServiceOfferingService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        *,
        offerings_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._offerings_factory = offerings_factory or (
            lambda uow: PostgresServiceOfferingRepository(uow.connection)
        )

    @staticmethod
    def _read(value: ServiceOffering) -> dict[str, Any]:
        return OfferingRead.model_validate(value.__dict__).model_dump(mode="json")

    def create(self, principal: Principal, body: OfferingCreate) -> dict[str, Any]:
        with self._uow_factory() as uow:
            value = self._offerings_factory(uow).create(
                NewServiceOffering(principal.user_id, body.name, body.description)
            )
            response = self._read(value)
            uow.commit()
            return response

    def list(self, principal: Principal, *, limit: int, offset: int) -> dict[str, Any]:
        if page := empty_page(offset, limit):
            return page
        with self._uow_factory() as uow:
            page = self._offerings_factory(uow).list_owned(
                principal.user_id, limit=limit, offset=offset
            )
            return {
                "items": [self._read(item) for item in page.items],
                "offset": page.offset,
                "limit": page.limit,
                "has_more": page.has_more,
            }

    def get(self, principal: Principal, offering_id: UUID) -> dict[str, Any]:
        with self._uow_factory() as uow:
            value = self._offerings_factory(uow).get_owned(
                principal.user_id, offering_id
            )
            if value is None:
                raise NotFoundError("Offering not found")
            return self._read(value)

    def update(
        self, principal: Principal, offering_id: UUID, patch: OfferingPatch
    ) -> dict[str, Any]:
        values = patch.model_dump(exclude_unset=True)
        with self._uow_factory() as uow:
            value = self._offerings_factory(uow).update_owned(
                principal.user_id,
                offering_id,
                ServiceOfferingChanges(values, patch.supplied_fields),
            )
            if value is None:
                raise NotFoundError("Offering not found")
            response = self._read(value)
            if patch.supplied_fields:
                uow.commit()
            return response

    def delete(self, principal: Principal, offering_id: UUID) -> None:
        with self._uow_factory() as uow:
            if not self._offerings_factory(uow).delete_owned(
                principal.user_id, offering_id
            ):
                raise NotFoundError("Offering not found")
            uow.commit()

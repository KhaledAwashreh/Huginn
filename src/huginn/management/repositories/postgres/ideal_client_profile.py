"""PostgreSQL persistence for owner-scoped ideal client profiles."""

import json
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from huginn.management.domain.common import Page
from huginn.management.domain.ideal_client_profile import (
    IdealClientProfile,
    IdealClientProfileChanges,
    NewIdealClientProfile,
)
from huginn.management.errors.domain import ConflictError, ValidationDomainError
from huginn.management.repositories.postgres.row_models import IdealClientProfileRow
from huginn.management.repositories.protocols.ideal_client_profile import (
    IdealClientProfileRepository,
)


class PostgresIdealClientProfileRepository(IdealClientProfileRepository):
    _columns = (
        "id, user_id, name, industries, company_sizes, geographies, exclusions, "
        "created_at, updated_at"
    )
    _update_columns = {
        "name": "name",
        "industries": "industries",
        "company_sizes": "company_sizes",
        "geographies": "geographies",
        "exclusions": "exclusions",
    }
    _json_fields = {"industries", "company_sizes", "geographies", "exclusions"}

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> IdealClientProfile:
        profile = IdealClientProfile(
            row[0],
            row[1],
            row[2],
            tuple(row[3]),
            tuple(row[4]),
            tuple(row[5]),
            tuple(row[6]),
            row[7],
            row[8],
        )
        validated = IdealClientProfileRow.model_validate_json(
            json.dumps(profile.__dict__, default=str)
        )
        values = validated.model_dump(mode="json")
        return IdealClientProfile(
            validated.id,
            validated.user_id,
            validated.name,
            tuple(values["industries"]),
            tuple(values["company_sizes"]),
            tuple(values["geographies"]),
            tuple(values["exclusions"]),
            validated.created_at,
            validated.updated_at,
        )

    def _one(self, query: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def create(self, profile: NewIdealClientProfile) -> IdealClientProfile:
        row = self._one(
            "INSERT INTO operational.ideal_client_profiles "
            "(user_id,name,industries,company_sizes,geographies,exclusions) "
            f"VALUES (%s,%s,%s,%s,%s,%s) RETURNING {self._columns}",
            (
                profile.user_id,
                profile.name,
                Jsonb(list(profile.industries)),
                Jsonb(list(profile.company_sizes)),
                Jsonb(list(profile.geographies)),
                Jsonb(list(profile.exclusions)),
            ),
        )
        assert row is not None
        return self._map(row)

    def get_owned(self, user_id: UUID, profile_id: UUID) -> IdealClientProfile | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.ideal_client_profiles "
            "WHERE user_id=%s AND id=%s",
            (user_id, profile_id),
        )
        return self._map(row) if row else None

    def list_owned(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> Page[IdealClientProfile]:
        rows = self.connection.execute(
            f"SELECT {self._columns} FROM operational.ideal_client_profiles "
            "WHERE user_id=%s ORDER BY created_at,id LIMIT %s OFFSET %s",
            (user_id, limit + 1, offset),
        ).fetchall()
        return Page(
            tuple(self._map(row) for row in rows[:limit]),
            offset,
            limit,
            len(rows) > limit,
        )

    def update_owned(
        self,
        user_id: UUID,
        profile_id: UUID,
        changes: IdealClientProfileChanges,
    ) -> IdealClientProfile | None:
        supplied = changes.supplied_fields
        if not supplied:
            return self.get_owned(user_id, profile_id)
        if not supplied <= self._update_columns.keys():
            raise ValueError("unsupported ICP update field")
        ordered = sorted(supplied)
        assignments = ", ".join(
            f"{self._update_columns[field]}=%s" for field in ordered
        )
        values = tuple(
            Jsonb(list(changes.values[field]))
            if field in self._json_fields
            else changes.values[field]
            for field in ordered
        )
        row = self._one(
            f"UPDATE operational.ideal_client_profiles SET {assignments}, "
            f"updated_at=clock_timestamp() WHERE user_id=%s AND id=%s RETURNING {self._columns}",
            (*values, user_id, profile_id),
        )
        return self._map(row) if row else None

    def delete_owned(self, user_id: UUID, profile_id: UUID) -> bool:
        try:
            row = self._one(
                "DELETE FROM operational.ideal_client_profiles "
                "WHERE user_id=%s AND id=%s RETURNING id",
                (user_id, profile_id),
            )
        except psycopg.IntegrityError as exc:
            if getattr(exc, "sqlstate", None) == "23503":
                raise ConflictError("ICP is referenced") from exc
            raise ValidationDomainError("ICP violates a database constraint") from exc
        return row is not None

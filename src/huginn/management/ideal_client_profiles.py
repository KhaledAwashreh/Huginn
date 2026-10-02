"""Owned IdealClientProfile persistence, evaluation guard, and use cases."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from huginn.management.domain import (
    ConflictError,
    IdealClientProfile,
    IdealClientProfileChanges,
    NewIdealClientProfile,
    NotFoundError,
    Page,
    Principal,
    ValidationDomainError,
)
from huginn.management.pagination import empty_page
from huginn.management.schemas import IcpCreate, IcpPatch, IcpRead


class PostgresIdealClientProfileRepository:
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
        raw = IdealClientProfile(
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
        IcpRead.model_validate_json(
            json.dumps(
                {
                    **raw.__dict__,
                    "industries": list(raw.industries),
                    "company_sizes": list(raw.company_sizes),
                    "geographies": list(raw.geographies),
                    "exclusions": list(raw.exclusions),
                },
                default=str,
            )
        )
        return raw

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


@dataclass(frozen=True)
class IcpCandidateFilter:
    industries: tuple[dict[str, Any], ...]
    company_sizes: tuple[dict[str, Any], ...]
    geographies: tuple[dict[str, Any], ...]
    exclusions: tuple[dict[str, Any], ...]


class CandidateRepository(Protocol):
    def find_candidates(self, criteria: IcpCandidateFilter) -> list[Any]: ...


def evaluate_icp(
    profile: IdealClientProfile, candidates: CandidateRepository
) -> list[Any]:
    """Guard incomplete ICPs before candidate selection.

    Separate collections encode OR within each dimension and AND across the
    three dimensions. Exclusions remain a single global veto collection.
    """
    if not profile.industries or not profile.company_sizes or not profile.geographies:
        return []
    return candidates.find_candidates(
        IcpCandidateFilter(
            profile.industries,
            profile.company_sizes,
            profile.geographies,
            profile.exclusions,
        )
    )


class IdealClientProfileService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        *,
        profiles_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._profiles_factory = profiles_factory or (
            lambda uow: PostgresIdealClientProfileRepository(uow.connection)
        )

    @staticmethod
    def _read(value: IdealClientProfile) -> dict[str, Any]:
        return IcpRead.model_validate_json(
            json.dumps(
                {
                    **value.__dict__,
                    "industries": list(value.industries),
                    "company_sizes": list(value.company_sizes),
                    "geographies": list(value.geographies),
                    "exclusions": list(value.exclusions),
                },
                default=str,
            )
        ).model_dump(mode="json")

    @staticmethod
    def _collections(body: IcpCreate | IcpPatch) -> dict[str, Any]:
        result = body.model_dump(mode="json", exclude_unset=True)
        return result

    def create(self, principal: Principal, body: IcpCreate) -> dict[str, Any]:
        data = body.model_dump(mode="json")
        with self._uow_factory() as uow:
            value = self._profiles_factory(uow).create(
                NewIdealClientProfile(
                    principal.user_id,
                    data["name"],
                    tuple(data["industries"]),
                    tuple(data["company_sizes"]),
                    tuple(data["geographies"]),
                    tuple(data["exclusions"]),
                )
            )
            response = self._read(value)
            uow.commit()
            return response

    def list(self, principal: Principal, *, limit: int, offset: int) -> dict[str, Any]:
        if page := empty_page(offset, limit):
            return page
        with self._uow_factory() as uow:
            page = self._profiles_factory(uow).list_owned(
                principal.user_id, limit=limit, offset=offset
            )
            return {
                "items": [self._read(item) for item in page.items],
                "offset": page.offset,
                "limit": page.limit,
                "has_more": page.has_more,
            }

    def get(self, principal: Principal, profile_id: UUID) -> dict[str, Any]:
        with self._uow_factory() as uow:
            value = self._profiles_factory(uow).get_owned(principal.user_id, profile_id)
            if value is None:
                raise NotFoundError("ICP not found")
            return self._read(value)

    def update(
        self, principal: Principal, profile_id: UUID, patch: IcpPatch
    ) -> dict[str, Any]:
        data = self._collections(patch)
        with self._uow_factory() as uow:
            value = self._profiles_factory(uow).update_owned(
                principal.user_id,
                profile_id,
                IdealClientProfileChanges(data, patch.supplied_fields),
            )
            if value is None:
                raise NotFoundError("ICP not found")
            response = self._read(value)
            if patch.supplied_fields:
                uow.commit()
            return response

    def delete(self, principal: Principal, profile_id: UUID) -> None:
        with self._uow_factory() as uow:
            if not self._profiles_factory(uow).delete_owned(
                principal.user_id, profile_id
            ):
                raise NotFoundError("ICP not found")
            uow.commit()

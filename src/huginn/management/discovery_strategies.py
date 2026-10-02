"""Owned ClientDiscoveryStrategy persistence and use cases."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

import psycopg

from huginn.management.domain import (
    ClientDiscoveryStrategy,
    ClientDiscoveryStrategyChanges,
    NewClientDiscoveryStrategy,
    NotFoundError,
    Page,
    Principal,
    ValidationDomainError,
)
from huginn.management.ideal_client_profiles import (
    PostgresIdealClientProfileRepository,
)
from huginn.management.pagination import empty_page
from huginn.management.schemas import StrategyCreate, StrategyPatch, StrategyRead
from huginn.management.service_offerings import PostgresServiceOfferingRepository


class PostgresClientDiscoveryStrategyRepository:
    _columns = (
        "id,user_id,name,service_offering_id,ideal_client_profile_id,is_active,"
        "created_at,updated_at"
    )
    _update_columns = {
        "name": "name",
        "service_offering_id": "service_offering_id",
        "ideal_client_profile_id": "ideal_client_profile_id",
        "is_active": "is_active",
    }

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> ClientDiscoveryStrategy:
        value = ClientDiscoveryStrategy(*row)
        StrategyRead.model_validate(value.__dict__)
        return value

    def _one(self, query: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchone()
        except psycopg.IntegrityError as exc:
            if getattr(exc, "sqlstate", None) == "23503":
                raise NotFoundError("Strategy reference not found") from exc
            raise ValidationDomainError(
                "strategy violates a database constraint"
            ) from exc

    def create(self, strategy: NewClientDiscoveryStrategy) -> ClientDiscoveryStrategy:
        row = self._one(
            "INSERT INTO operational.client_discovery_strategies "
            "(user_id,name,service_offering_id,ideal_client_profile_id,is_active) "
            f"VALUES (%s,%s,%s,%s,%s) RETURNING {self._columns}",
            (
                strategy.user_id,
                strategy.name,
                strategy.service_offering_id,
                strategy.ideal_client_profile_id,
                strategy.is_active,
            ),
        )
        assert row is not None
        return self._map(row)

    def get_owned(
        self, user_id: UUID, strategy_id: UUID
    ) -> ClientDiscoveryStrategy | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.client_discovery_strategies "
            "WHERE user_id=%s AND id=%s",
            (user_id, strategy_id),
        )
        return self._map(row) if row else None

    def list_owned(
        self,
        user_id: UUID,
        *,
        limit: int,
        offset: int,
        active: bool | None = None,
    ) -> Page[ClientDiscoveryStrategy]:
        predicate = "user_id=%s"
        params: list[Any] = [user_id]
        if active is not None:
            predicate += " AND is_active=%s"
            params.append(active)
        rows = self.connection.execute(
            f"SELECT {self._columns} FROM operational.client_discovery_strategies "
            f"WHERE {predicate} ORDER BY created_at,id LIMIT %s OFFSET %s",
            (*params, limit + 1, offset),
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
        strategy_id: UUID,
        changes: ClientDiscoveryStrategyChanges,
    ) -> ClientDiscoveryStrategy | None:
        supplied = changes.supplied_fields
        if not supplied:
            return self.get_owned(user_id, strategy_id)
        if not supplied <= self._update_columns.keys():
            raise ValueError("unsupported strategy update field")
        ordered = sorted(supplied)
        assignments = ", ".join(
            f"{self._update_columns[field]}=%s" for field in ordered
        )
        row = self._one(
            f"UPDATE operational.client_discovery_strategies SET {assignments}, "
            f"updated_at=clock_timestamp() WHERE user_id=%s AND id=%s RETURNING {self._columns}",
            (*(changes.values[field] for field in ordered), user_id, strategy_id),
        )
        return self._map(row) if row else None

    def delete_owned(self, user_id: UUID, strategy_id: UUID) -> bool:
        row = self._one(
            "DELETE FROM operational.client_discovery_strategies "
            "WHERE user_id=%s AND id=%s RETURNING id",
            (user_id, strategy_id),
        )
        return row is not None


class ClientDiscoveryStrategyService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        *,
        strategies_factory: Callable[[Any], Any] | None = None,
        offerings_factory: Callable[[Any], Any] | None = None,
        profiles_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._strategies_factory = strategies_factory or (
            lambda uow: PostgresClientDiscoveryStrategyRepository(uow.connection)
        )
        self._offerings_factory = offerings_factory or (
            lambda uow: PostgresServiceOfferingRepository(uow.connection)
        )
        self._profiles_factory = profiles_factory or (
            lambda uow: PostgresIdealClientProfileRepository(uow.connection)
        )

    @staticmethod
    def _read(value: ClientDiscoveryStrategy) -> dict[str, Any]:
        return StrategyRead.model_validate(value.__dict__).model_dump(mode="json")

    def _require_references(
        self, uow: Any, user_id: UUID, offering_id: UUID, profile_id: UUID
    ) -> None:
        if self._offerings_factory(uow).get_owned(user_id, offering_id) is None:
            raise NotFoundError("Strategy reference not found")
        if self._profiles_factory(uow).get_owned(user_id, profile_id) is None:
            raise NotFoundError("Strategy reference not found")

    def create(self, principal: Principal, body: StrategyCreate) -> dict[str, Any]:
        with self._uow_factory() as uow:
            self._require_references(
                uow,
                principal.user_id,
                body.service_offering_id,
                body.ideal_client_profile_id,
            )
            value = self._strategies_factory(uow).create(
                NewClientDiscoveryStrategy(
                    principal.user_id,
                    body.name,
                    body.service_offering_id,
                    body.ideal_client_profile_id,
                    body.is_active,
                )
            )
            response = self._read(value)
            uow.commit()
            return response

    def list(
        self,
        principal: Principal,
        *,
        limit: int,
        offset: int,
        active: bool | None,
    ) -> dict[str, Any]:
        if page := empty_page(offset, limit):
            return page
        with self._uow_factory() as uow:
            page = self._strategies_factory(uow).list_owned(
                principal.user_id, limit=limit, offset=offset, active=active
            )
            return {
                "items": [self._read(item) for item in page.items],
                "offset": page.offset,
                "limit": page.limit,
                "has_more": page.has_more,
            }

    def get(self, principal: Principal, strategy_id: UUID) -> dict[str, Any]:
        with self._uow_factory() as uow:
            value = self._strategies_factory(uow).get_owned(
                principal.user_id, strategy_id
            )
            if value is None:
                raise NotFoundError("Strategy not found")
            return self._read(value)

    def update(
        self, principal: Principal, strategy_id: UUID, patch: StrategyPatch
    ) -> dict[str, Any]:
        data = patch.model_dump(exclude_unset=True)
        with self._uow_factory() as uow:
            strategies = self._strategies_factory(uow)
            current = strategies.get_owned(principal.user_id, strategy_id)
            if current is None:
                raise NotFoundError("Strategy not found")
            offering_id = data.get("service_offering_id", current.service_offering_id)
            profile_id = data.get(
                "ideal_client_profile_id", current.ideal_client_profile_id
            )
            if {
                "service_offering_id",
                "ideal_client_profile_id",
            } & patch.supplied_fields:
                self._require_references(
                    uow, principal.user_id, offering_id, profile_id
                )
            value = strategies.update_owned(
                principal.user_id,
                strategy_id,
                ClientDiscoveryStrategyChanges(data, patch.supplied_fields),
            )
            if value is None:
                raise NotFoundError("Strategy not found")
            response = self._read(value)
            if patch.supplied_fields:
                uow.commit()
            return response

    def delete(self, principal: Principal, strategy_id: UUID) -> None:
        with self._uow_factory() as uow:
            if not self._strategies_factory(uow).delete_owned(
                principal.user_id, strategy_id
            ):
                raise NotFoundError("Strategy not found")
            uow.commit()

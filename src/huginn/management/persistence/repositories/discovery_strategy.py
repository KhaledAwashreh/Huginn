"""PostgreSQL persistence for owner-scoped discovery strategies."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.client_discovery_strategy import (
    ClientDiscoveryStrategy,
)
from huginn.management.domain.errors.errors import NotFoundError, ValidationDomainError
from huginn.management.domain.value_objects.client_discovery_strategy import (
    ClientDiscoveryStrategyChanges,
    NewClientDiscoveryStrategy,
)
from huginn.management.domain.value_objects.common import Page
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.repositories.discovery_strategy import (
    ClientDiscoveryStrategyRepository,
)
from huginn.management.persistence.errors.database import IntegrityError
from huginn.management.persistence.row_models.resources import (
    ClientDiscoveryStrategyRow,
)


class PostgresClientDiscoveryStrategyRepository(ClientDiscoveryStrategyRepository):
    _columns = (
        "id,business_id,name,service_offering_id,ideal_client_profile_id,is_active,"
        "created_at,updated_at"
    )
    _update_columns = {
        "name": "name",
        "service_offering_id": "service_offering_id",
        "ideal_client_profile_id": "ideal_client_profile_id",
        "is_active": "is_active",
    }

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> ClientDiscoveryStrategy:
        value = ClientDiscoveryStrategy(*row)
        validated = ClientDiscoveryStrategyRow.model_validate(value.__dict__)
        return ClientDiscoveryStrategy(
            validated.id,
            validated.business_id,
            validated.name,
            validated.service_offering_id,
            validated.ideal_client_profile_id,
            validated.is_active,
            validated.created_at,
            validated.updated_at,
        )

    def _one(self, query: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchone()
        except IntegrityError as exc:
            if getattr(exc, "sqlstate", None) == "23503":
                raise NotFoundError("Strategy reference not found") from exc
            raise ValidationDomainError(
                "strategy violates a database constraint"
            ) from exc

    def _lock_configuration(self, business_id: UUID) -> None:
        # Readers hold FOR SHARE through generation/publication; writers serialize.
        self.connection.execute(
            "SELECT id FROM operational.businesses WHERE id=%s FOR UPDATE",
            (business_id,),
        ).fetchone()

    def set_single_configuration(
        self, business_id: UUID, offering_id: UUID, profile_id: UUID
    ) -> ClientDiscoveryStrategy:
        self._lock_configuration(business_id)
        row = self._one(
            f"SELECT {self._columns} FROM operational.client_discovery_strategies "
            "WHERE business_id=%s AND service_offering_id=%s "
            "AND ideal_client_profile_id=%s "
            "ORDER BY is_active DESC,created_at,id LIMIT 1 FOR UPDATE",
            (business_id, offering_id, profile_id),
        )
        current = self._map(row) if row else None
        self.connection.execute(
            "UPDATE operational.client_discovery_strategies "
            "SET is_active=false,updated_at=clock_timestamp() "
            "WHERE business_id=%s AND is_active AND id IS DISTINCT FROM %s",
            (business_id, current.id if current else None),
        )
        if current is None:
            return self.create(
                NewClientDiscoveryStrategy(
                    business_id, "Discovery", offering_id, profile_id, True
                )
            )
        if current.is_active:
            return current
        value = self.update_owned(
            business_id,
            current.id,
            ClientDiscoveryStrategyChanges(
                {"is_active": True}, frozenset({"is_active"})
            ),
        )
        assert value is not None
        return value

    def create(self, strategy: NewClientDiscoveryStrategy) -> ClientDiscoveryStrategy:
        self._lock_configuration(strategy.business_id)
        row = self._one(
            "INSERT INTO operational.client_discovery_strategies "
            "(business_id,name,service_offering_id,ideal_client_profile_id,is_active) "
            f"VALUES (%s,%s,%s,%s,%s) RETURNING {self._columns}",
            (
                strategy.business_id,
                strategy.name,
                strategy.service_offering_id,
                strategy.ideal_client_profile_id,
                strategy.is_active,
            ),
        )
        assert row is not None
        return self._map(row)

    def get_owned(
        self, business_id: UUID, strategy_id: UUID
    ) -> ClientDiscoveryStrategy | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.client_discovery_strategies "
            "WHERE business_id=%s AND id=%s",
            (business_id, strategy_id),
        )
        return self._map(row) if row else None

    def list_owned(
        self,
        business_id: UUID,
        *,
        limit: int,
        offset: int,
        active: bool | None = None,
    ) -> Page[ClientDiscoveryStrategy]:
        predicate = "business_id=%s"
        params: list[Any] = [business_id]
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
        business_id: UUID,
        strategy_id: UUID,
        changes: ClientDiscoveryStrategyChanges,
    ) -> ClientDiscoveryStrategy | None:
        supplied = changes.supplied_fields
        if not supplied:
            return self.get_owned(business_id, strategy_id)
        if not supplied <= self._update_columns.keys():
            raise ValueError("unsupported strategy update field")
        self._lock_configuration(business_id)
        ordered = sorted(supplied)
        assignments = ", ".join(
            f"{self._update_columns[field]}=%s" for field in ordered
        )
        row = self._one(
            f"UPDATE operational.client_discovery_strategies SET {assignments}, "
            f"updated_at=clock_timestamp() WHERE business_id=%s AND id=%s RETURNING {self._columns}",
            (*(changes.values[field] for field in ordered), business_id, strategy_id),
        )
        return self._map(row) if row else None

    def delete_owned(self, business_id: UUID, strategy_id: UUID) -> bool:
        self._lock_configuration(business_id)
        row = self._one(
            "DELETE FROM operational.client_discovery_strategies "
            "WHERE business_id=%s AND id=%s RETURNING id",
            (business_id, strategy_id),
        )
        return row is not None

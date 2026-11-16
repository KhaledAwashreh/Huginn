"""PostgreSQL adapter for Business-scoped suppression history."""

from datetime import datetime
from typing import Any
from uuid import UUID

from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.repositories.suppression_block import (
    SuppressionBlockRepository,
)
from huginn.management.persistence.errors.database import IntegrityError


class PostgresSuppressionBlockRepository(SuppressionBlockRepository):
    _columns = (
        "id,business_id,company_id,kind,created_at,effective_at,created_by_user_id,"
        "expires_at,cleared_at,cleared_by_user_id,reason,version"
    )

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> SuppressionBlock:
        return SuppressionBlock(
            id=row[0],
            business_id=row[1],
            company_id=row[2],
            kind=SuppressionKind(row[3]),
            created_at=row[4],
            effective_at=row[5],
            created_by_user_id=row[6],
            expires_at=row[7],
            cleared_at=row[8],
            cleared_by_user_id=row[9],
            reason=row[10],
            version=row[11],
        )

    def list_active(
        self, business_id: UUID, company_id: UUID, at: datetime
    ) -> tuple[SuppressionBlock, ...]:
        rows = self.connection.execute(
            f"SELECT {self._columns} FROM operational.suppression_blocks "
            "WHERE business_id=%s AND company_id=%s AND cleared_at IS NULL "
            "AND effective_at<=%s AND (expires_at IS NULL OR %s<expires_at) "
            "ORDER BY created_at,id",
            (business_id, company_id, at, at),
        ).fetchall()
        return tuple(self._map(row) for row in rows)

    def list_history(
        self, business_id: UUID, company_id: UUID
    ) -> tuple[SuppressionBlock, ...]:
        rows = self.connection.execute(
            f"SELECT {self._columns} FROM operational.suppression_blocks "
            "WHERE business_id=%s AND company_id=%s ORDER BY created_at,id",
            (business_id, company_id),
        ).fetchall()
        return tuple(self._map(row) for row in rows)

    def get_owned(self, business_id: UUID, block_id: UUID) -> SuppressionBlock | None:
        row = self.connection.execute(
            f"SELECT {self._columns} FROM operational.suppression_blocks "
            "WHERE business_id=%s AND id=%s",
            (business_id, block_id),
        ).fetchone()
        return self._map(row) if row else None

    def append(self, block: SuppressionBlock) -> SuppressionBlock:
        try:
            row = self.connection.execute(
                f"INSERT INTO operational.suppression_blocks ({self._columns}) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                f"RETURNING {self._columns}",
                (
                    block.id,
                    block.business_id,
                    block.company_id,
                    block.kind.value,
                    block.created_at,
                    block.effective_at,
                    block.created_by_user_id,
                    block.expires_at,
                    block.cleared_at,
                    block.cleared_by_user_id,
                    block.reason,
                    block.version,
                ),
            ).fetchone()
        except IntegrityError as exc:
            if exc.sqlstate == "23505":
                raise ConflictError("Suppression block already exists") from exc
            raise ValidationDomainError(
                "Suppression block violates a persistence constraint"
            ) from exc
        assert row is not None
        return self._map(row)

    def clear_one(
        self,
        business_id: UUID,
        company_id: UUID,
        block_id: UUID,
        expected_version: int,
        actor_user_id: UUID,
        cleared_at: datetime,
    ) -> SuppressionBlock:
        row = self.connection.execute(
            f"UPDATE operational.suppression_blocks SET cleared_at=%s,"
            "cleared_by_user_id=%s,version=version+1 "
            "WHERE business_id=%s AND company_id=%s AND id=%s AND version=%s "
            "AND cleared_at IS NULL "
            f"RETURNING {self._columns}",
            (
                cleared_at,
                actor_user_id,
                business_id,
                company_id,
                block_id,
                expected_version,
            ),
        ).fetchone()
        if row:
            return self._map(row)
        raise ConflictError("Suppression block changed or is outside this scope")

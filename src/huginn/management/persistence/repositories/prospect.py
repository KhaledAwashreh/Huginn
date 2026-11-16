"""PostgreSQL adapter for Business/Company prospect relationships."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.errors.errors import (
    ConflictError,
    NotFoundError,
    ValidationDomainError,
)
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.repositories.prospect import (
    ProspectRepository,
)
from huginn.management.persistence.errors.database import IntegrityError


class PostgresProspectRepository(ProspectRepository):
    _columns = (
        "id,business_id,company_id,stage,created_at,updated_at,version,notes,"
        "follow_up_at,last_active_stage"
    )

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> Prospect:
        return Prospect(
            id=row[0],
            business_id=row[1],
            company_id=row[2],
            stage=ProspectStage(row[3]),
            created_at=row[4],
            updated_at=row[5],
            version=row[6],
            notes=row[7],
            follow_up_at=row[8],
            last_active_stage=ProspectStage(row[9]) if row[9] else None,
        )

    def get_owned(self, business_id: UUID, prospect_id: UUID) -> Prospect | None:
        row = self.connection.execute(
            f"SELECT {self._columns} FROM operational.prospects "
            "WHERE business_id=%s AND id=%s",
            (business_id, prospect_id),
        ).fetchone()
        return self._map(row) if row else None

    def get_by_business_company(
        self, business_id: UUID, company_id: UUID
    ) -> Prospect | None:
        row = self.connection.execute(
            f"SELECT {self._columns} FROM operational.prospects "
            "WHERE business_id=%s AND company_id=%s",
            (business_id, company_id),
        ).fetchone()
        return self._map(row) if row else None

    def create(self, prospect: Prospect) -> Prospect:
        try:
            row = self.connection.execute(
                f"INSERT INTO operational.prospects ({self._columns}) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (business_id,company_id) DO NOTHING "
                f"RETURNING {self._columns}",
                (
                    prospect.id,
                    prospect.business_id,
                    prospect.company_id,
                    prospect.stage.value,
                    prospect.created_at,
                    prospect.updated_at,
                    prospect.version,
                    prospect.notes,
                    prospect.follow_up_at,
                    prospect.last_active_stage.value
                    if prospect.last_active_stage
                    else None,
                ),
            ).fetchone()
        except IntegrityError as exc:
            if exc.sqlstate == "23505":
                raise ConflictError("Prospect identity already exists") from exc
            raise ValidationDomainError(
                "Prospect violates a persistence constraint"
            ) from exc
        if row:
            return self._map(row)
        existing = self.get_by_business_company(
            prospect.business_id, prospect.company_id
        )
        if existing is None:
            raise ConflictError("Prospect was concurrently changed")
        return existing

    def update_owned(
        self,
        business_id: UUID,
        prospect_id: UUID,
        expected_version: int,
        prospect: Prospect,
    ) -> Prospect:
        if prospect.business_id != business_id:
            raise NotFoundError("Prospect not found")
        if prospect.id != prospect_id:
            raise ValidationDomainError(
                "Prospect update identity does not match its scope"
            )
        row = self.connection.execute(
            f"UPDATE operational.prospects SET stage=%s,updated_at=%s,version=version+1,"
            "notes=%s,follow_up_at=%s,last_active_stage=%s "
            "WHERE business_id=%s AND id=%s AND version=%s "
            "AND company_id=%s AND updated_at<=%s "
            f"RETURNING {self._columns}",
            (
                prospect.stage.value,
                prospect.updated_at,
                prospect.notes,
                prospect.follow_up_at,
                prospect.last_active_stage.value
                if prospect.last_active_stage
                else None,
                business_id,
                prospect_id,
                expected_version,
                prospect.company_id,
                prospect.updated_at,
            ),
        ).fetchone()
        if row:
            return self._map(row)
        if self.get_owned(business_id, prospect_id) is None:
            raise NotFoundError("Prospect not found")
        raise ConflictError("Prospect changed before the command completed")

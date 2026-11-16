"""PostgreSQL adapter for immutable discovery origins of a prospect."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.prospect_origin import ProspectOrigin
from huginn.management.domain.errors.errors import (
    ConflictError,
    NotFoundError,
    ValidationDomainError,
)
from huginn.management.domain.value_objects.origin_append_result import (
    OriginAppendResult,
)
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.repositories.prospect_origin import (
    ProspectOriginRepository,
)
from huginn.management.persistence.errors.database import IntegrityError


class PostgresProspectOriginRepository(ProspectOriginRepository):
    _columns = (
        "id,business_id,company_id,prospect_id,recommendation_id,"
        "assessment_revision_id,created_by_user_id,created_at"
    )

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> ProspectOrigin:
        return ProspectOrigin(*row)

    def list_for_prospects(
        self, business_id: UUID, prospect_ids: tuple[UUID, ...]
    ) -> tuple[ProspectOrigin, ...]:
        if not prospect_ids:
            return ()
        rows = self.connection.execute(
            f"SELECT {self._columns} FROM operational.prospect_origins "
            "WHERE business_id=%s AND prospect_id=ANY(%s::uuid[]) "
            "ORDER BY prospect_id,created_at,id",
            (business_id, list(prospect_ids)),
        ).fetchall()
        return tuple(self._map(row) for row in rows)

    def list_owned(
        self, business_id: UUID, prospect_id: UUID
    ) -> tuple[ProspectOrigin, ...]:
        return self.list_for_prospects(business_id, (prospect_id,))

    def append_if_absent(self, origin: ProspectOrigin) -> OriginAppendResult:
        membership = self.connection.execute(
            "SELECT 1 FROM operational.prospects prospect "
            "JOIN operational.recommendations recommendation "
            "ON recommendation.id=%s AND recommendation.business_id=prospect.business_id "
            "AND recommendation.company_id=prospect.company_id "
            "JOIN operational.assessment_revisions revision "
            "ON revision.recommendation_id=recommendation.id "
            "AND revision.business_id=recommendation.business_id "
            "AND revision.company_id=recommendation.company_id "
            "AND revision.id=%s "
            "JOIN operational.businesses business "
            "ON business.id=prospect.business_id AND business.owner_user_id=%s "
            "WHERE prospect.id=%s AND prospect.business_id=%s "
            "AND prospect.company_id=%s",
            (
                origin.recommendation_id,
                origin.assessment_revision_id,
                origin.created_by_user_id,
                origin.prospect_id,
                origin.business_id,
                origin.company_id,
            ),
        ).fetchone()
        if membership is None:
            raise NotFoundError(
                "Origin membership is not owned by this Business and Company"
            )
        try:
            row = self.connection.execute(
                f"INSERT INTO operational.prospect_origins ({self._columns}) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (business_id,recommendation_id,assessment_revision_id,prospect_id) "
                "DO NOTHING "
                f"RETURNING {self._columns}",
                (
                    origin.id,
                    origin.business_id,
                    origin.company_id,
                    origin.prospect_id,
                    origin.recommendation_id,
                    origin.assessment_revision_id,
                    origin.created_by_user_id,
                    origin.created_at,
                ),
            ).fetchone()
        except IntegrityError as exc:
            if exc.sqlstate == "23505":
                raise ConflictError(
                    "Origin identity conflicts with existing history"
                ) from exc
            raise ValidationDomainError(
                "Origin violates a persistence constraint"
            ) from exc
        if row:
            return OriginAppendResult(self._map(row), True)
        existing = self.connection.execute(
            f"SELECT {self._columns} FROM operational.prospect_origins "
            "WHERE business_id=%s AND recommendation_id=%s "
            "AND assessment_revision_id=%s AND prospect_id=%s",
            (
                origin.business_id,
                origin.recommendation_id,
                origin.assessment_revision_id,
                origin.prospect_id,
            ),
        ).fetchone()
        if existing is None:
            raise ConflictError("Origin was concurrently changed")
        return OriginAppendResult(self._map(existing), False)

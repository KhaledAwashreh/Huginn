"""PostgreSQL adapter for Business-owned recommendation occurrences."""

from datetime import datetime
from typing import Any
from uuid import UUID

from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.errors.errors import (
    ConflictError,
    NotFoundError,
    ValidationDomainError,
)
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.repositories.recommendation import (
    RecommendationRepository,
)
from huginn.management.persistence.errors.database import IntegrityError


class PostgresRecommendationRepository(RecommendationRepository):
    _columns = (
        "id,business_id,company_id,status,created_at,updated_at,current_revision_id,"
        "first_presented_at,resolved_at,resolved_by_user_id,resolution_reason,version"
    )

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> Recommendation:
        return Recommendation(
            id=row[0],
            business_id=row[1],
            company_id=row[2],
            status=RecommendationStatus(row[3]),
            created_at=row[4],
            updated_at=row[5],
            current_revision_id=row[6],
            first_presented_at=row[7],
            resolved_at=row[8],
            resolved_by_user_id=row[9],
            resolution_reason=row[10],
            version=row[11],
        )

    def get_owned(
        self, business_id: UUID, recommendation_id: UUID
    ) -> Recommendation | None:
        row = self.connection.execute(
            f"SELECT {self._columns} FROM operational.recommendations "
            "WHERE business_id=%s AND id=%s",
            (business_id, recommendation_id),
        ).fetchone()
        return self._map(row) if row else None

    def get_open(self, business_id: UUID, company_id: UUID) -> Recommendation | None:
        row = self.connection.execute(
            f"SELECT {self._columns} FROM operational.recommendations "
            "WHERE business_id=%s AND company_id=%s AND status='open'",
            (business_id, company_id),
        ).fetchone()
        return self._map(row) if row else None

    def create_open(self, recommendation: Recommendation) -> Recommendation:
        if recommendation.status.value != "open":
            raise ValidationDomainError("Only open recommendations can be created")
        try:
            row = self.connection.execute(
                f"INSERT INTO operational.recommendations "
                f"({self._columns}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (business_id,company_id) WHERE status='open' DO NOTHING "
                f"RETURNING {self._columns}",
                (
                    recommendation.id,
                    recommendation.business_id,
                    recommendation.company_id,
                    recommendation.status.value,
                    recommendation.created_at,
                    recommendation.updated_at,
                    recommendation.current_revision_id,
                    recommendation.first_presented_at,
                    recommendation.resolved_at,
                    recommendation.resolved_by_user_id,
                    recommendation.resolution_reason,
                    recommendation.version,
                ),
            ).fetchone()
        except IntegrityError as exc:
            _raise_integrity(exc)
        if row:
            return self._map(row)
        existing = self.get_open(recommendation.business_id, recommendation.company_id)
        if existing is None:
            raise ConflictError("Open recommendation was concurrently changed")
        return existing

    def select_current_revision(
        self,
        business_id: UUID,
        recommendation_id: UUID,
        revision_id: UUID,
        expected_version: int,
    ) -> Recommendation:
        membership = self.connection.execute(
            "SELECT 1 FROM operational.assessment_revisions "
            "WHERE business_id=%s AND recommendation_id=%s AND id=%s",
            (business_id, recommendation_id, revision_id),
        ).fetchone()
        if membership is None:
            raise NotFoundError("Recommendation assessment not found")
        try:
            row = self.connection.execute(
                f"UPDATE operational.recommendations SET current_revision_id=%s,"
                "version=version+1,updated_at=GREATEST(updated_at,clock_timestamp()) "
                "WHERE business_id=%s AND id=%s AND status='open' AND version=%s "
                f"RETURNING {self._columns}",
                (revision_id, business_id, recommendation_id, expected_version),
            ).fetchone()
        except IntegrityError as exc:
            if exc.sqlstate == "23514":
                raise ConflictError(
                    "Recommendation revision selection is stale"
                ) from exc
            raise ValidationDomainError(
                "Recommendation revision selection violates a persistence constraint"
            ) from exc
        if row:
            return self._map(row)
        self._raise_missing_or_stale(business_id, recommendation_id)

    def record_confirmed_presentation(
        self,
        business_id: UUID,
        company_id: UUID,
        recommendation_id: UUID,
        cycle_id: UUID,
        revision_id: UUID,
        presented_at: datetime,
    ) -> Recommendation:
        confirmed = self.connection.execute(
            "SELECT 1 FROM operational.offer_cycles "
            "WHERE id=%s AND business_id=%s AND company_id=%s "
            "AND recommendation_id=%s AND selected_revision_id=%s "
            "AND status='confirmed' AND presented_at=%s",
            (
                cycle_id,
                business_id,
                company_id,
                recommendation_id,
                revision_id,
                presented_at,
            ),
        ).fetchone()
        if confirmed is None:
            raise NotFoundError("Confirmed recommendation presentation not found")
        row = self.connection.execute(
            f"UPDATE operational.recommendations AS recommendation "
            "SET first_presented_at=%s,"
            "version=version+1,updated_at=GREATEST(updated_at,%s) "
            "WHERE recommendation.business_id=%s AND recommendation.company_id=%s "
            "AND recommendation.id=%s AND recommendation.first_presented_at IS NULL "
            f"RETURNING {self._columns}",
            (
                presented_at,
                presented_at,
                business_id,
                company_id,
                recommendation_id,
            ),
        ).fetchone()
        if row:
            return self._map(row)
        existing = self.get_owned(business_id, recommendation_id)
        if existing is None:
            raise NotFoundError("Recommendation not found")
        return existing

    def resolve_owned(
        self,
        business_id: UUID,
        recommendation_id: UUID,
        expected_version: int,
        status: RecommendationStatus,
        actor_user_id: UUID,
        resolved_at: datetime,
        reason: str | None,
    ) -> Recommendation:
        if status.value not in {"converted", "rejected"}:
            raise ValidationDomainError("Resolution status must be terminal")
        owner = self.connection.execute(
            "SELECT 1 FROM operational.businesses WHERE id=%s AND owner_user_id=%s",
            (business_id, actor_user_id),
        ).fetchone()
        if owner is None:
            raise NotFoundError("Recommendation not found")
        row = self.connection.execute(
            f"UPDATE operational.recommendations SET status=%s,resolved_at=%s,"
            "resolved_by_user_id=%s,resolution_reason=%s,version=version+1,"
            "updated_at=GREATEST(updated_at,%s) "
            "WHERE business_id=%s AND id=%s AND status='open' AND version=%s "
            f"RETURNING {self._columns}",
            (
                status.value,
                resolved_at,
                actor_user_id,
                reason,
                resolved_at,
                business_id,
                recommendation_id,
                expected_version,
            ),
        ).fetchone()
        if row:
            return self._map(row)
        self._raise_missing_or_stale(business_id, recommendation_id)

    def _raise_missing_or_stale(self, business_id: UUID, recommendation_id: UUID):
        exists = self.connection.execute(
            "SELECT 1 FROM operational.recommendations WHERE business_id=%s AND id=%s",
            (business_id, recommendation_id),
        ).fetchone()
        if exists is None:
            raise NotFoundError("Recommendation not found")
        raise ConflictError("Recommendation changed before the command completed")


def _raise_integrity(exc: IntegrityError) -> None:
    if exc.sqlstate == "23505":
        raise ConflictError(
            "Recommendation conflicts with an existing occurrence"
        ) from exc
    raise ValidationDomainError(
        "Recommendation violates a persistence constraint"
    ) from exc

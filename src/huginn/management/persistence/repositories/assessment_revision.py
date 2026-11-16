"""PostgreSQL adapter for immutable recommendation assessment snapshots."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.errors.errors import (
    ConflictError,
    NotFoundError,
    ValidationDomainError,
)
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.domain.value_objects.strategy_assessment_snapshot import (
    StrategyAssessmentSnapshot,
)
from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)
from huginn.management.persistence.contracts.repositories.assessment_revision import (
    AssessmentRevisionRepository,
)
from huginn.management.persistence.errors.database import IntegrityError


class PostgresAssessmentRevisionRepository(AssessmentRevisionRepository):
    _columns = (
        "id,recommendation_id,business_id,company_id,revision_number,assessed_at,"
        "strategy_assessments,professional_profile_snapshot,evidence_snapshots,"
        "evidence_observation_ids,policy_versions,evaluation_seed,assessed_by_user_id"
    )

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> AssessmentRevision:
        associations = tuple(
            StrategyAssessmentSnapshot(
                strategy_id=UUID(item["strategy_id"]),
                offering_id=UUID(item["offering_id"]),
                ideal_client_profile_id=UUID(item["ideal_client_profile_id"]),
                strategy_snapshot=JsonSnapshot(item["strategy_snapshot"]),
                offering_snapshot=JsonSnapshot(item["offering_snapshot"]),
                ideal_client_profile_snapshot=JsonSnapshot(
                    item["ideal_client_profile_snapshot"]
                ),
                assessment_snapshot=JsonSnapshot(item["assessment_snapshot"]),
            )
            for item in row[6]
        )
        return AssessmentRevision(
            id=row[0],
            recommendation_id=row[1],
            business_id=row[2],
            company_id=row[3],
            revision_number=row[4],
            assessed_at=row[5],
            strategy_assessments=associations,
            professional_profile_snapshot=JsonSnapshot(row[7]),
            evidence_snapshots=tuple(JsonSnapshot(item) for item in row[8]),
            evidence_observation_ids=tuple(row[9]),
            policy_versions=tuple(row[10]),
            evaluation_seed=row[11],
            assessed_by_user_id=row[12],
        )

    def get_many_owned(
        self, business_id: UUID, revision_ids: tuple[UUID, ...]
    ) -> tuple[AssessmentRevision, ...]:
        if not revision_ids:
            return ()
        rows = self.connection.execute(
            f"SELECT {self._columns} FROM operational.assessment_revisions "
            "WHERE business_id=%s AND id=ANY(%s::uuid[])",
            (business_id, list(revision_ids)),
        ).fetchall()
        return tuple(self._map(row) for row in rows)

    def get_owned(
        self, business_id: UUID, recommendation_id: UUID, revision_id: UUID
    ) -> AssessmentRevision | None:
        row = self.connection.execute(
            f"SELECT {self._columns} FROM operational.assessment_revisions "
            "WHERE business_id=%s AND recommendation_id=%s AND id=%s",
            (business_id, recommendation_id, revision_id),
        ).fetchone()
        return self._map(row) if row else None

    def list_history(
        self, business_id: UUID, recommendation_id: UUID
    ) -> tuple[AssessmentRevision, ...]:
        rows = self.connection.execute(
            f"SELECT {self._columns} FROM operational.assessment_revisions "
            "WHERE business_id=%s AND recommendation_id=%s "
            "ORDER BY revision_number,id",
            (business_id, recommendation_id),
        ).fetchall()
        return tuple(self._map(row) for row in rows)

    def append(self, revision: AssessmentRevision) -> AssessmentRevision:
        recommendation = self.connection.execute(
            "SELECT 1 FROM operational.recommendations "
            "WHERE id=%s AND business_id=%s AND company_id=%s",
            (revision.recommendation_id, revision.business_id, revision.company_id),
        ).fetchone()
        if recommendation is None:
            raise NotFoundError(
                "Recommendation not found for this Business and Company"
            )
        if revision.assessed_by_user_id is not None:
            owner = self.connection.execute(
                "SELECT 1 FROM operational.businesses WHERE id=%s AND owner_user_id=%s",
                (revision.business_id, revision.assessed_by_user_id),
            ).fetchone()
            if owner is None:
                raise NotFoundError("Recommendation not found for this Business")
        strategy_assessments = [
            {
                "strategy_id": str(item.strategy_id),
                "offering_id": str(item.offering_id),
                "ideal_client_profile_id": str(item.ideal_client_profile_id),
                "strategy_snapshot": item.strategy_snapshot.to_json_object(),
                "offering_snapshot": item.offering_snapshot.to_json_object(),
                "ideal_client_profile_snapshot": item.ideal_client_profile_snapshot.to_json_object(),
                "assessment_snapshot": item.assessment_snapshot.to_json_object(),
            }
            for item in revision.strategy_assessments
        ]
        try:
            row = self.connection.execute(
                f"INSERT INTO operational.assessment_revisions ({self._columns}) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING "
                f"RETURNING {self._columns}",
                (
                    revision.id,
                    revision.recommendation_id,
                    revision.business_id,
                    revision.company_id,
                    revision.revision_number,
                    revision.assessed_at,
                    JsonParameter(strategy_assessments),
                    JsonParameter(
                        revision.professional_profile_snapshot.to_json_object()
                    ),
                    JsonParameter(
                        [item.to_json_object() for item in revision.evidence_snapshots]
                    ),
                    list(revision.evidence_observation_ids),
                    list(revision.policy_versions),
                    revision.evaluation_seed,
                    revision.assessed_by_user_id,
                ),
            ).fetchone()
        except IntegrityError as exc:
            if exc.sqlstate == "23505":
                raise ConflictError("Assessment revision already exists") from exc
            raise ValidationDomainError(
                "Assessment revision violates a persistence constraint"
            ) from exc
        if row is None:
            raise ConflictError("Assessment revision already exists")
        return self._map(row)

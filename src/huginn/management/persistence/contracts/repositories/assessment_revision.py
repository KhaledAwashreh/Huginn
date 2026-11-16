from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.assessment_revision import AssessmentRevision


class AssessmentRevisionRepository(Protocol):
    def get_owned(
        self, business_id: UUID, recommendation_id: UUID, revision_id: UUID
    ) -> AssessmentRevision | None: ...
    def list_history(
        self, business_id: UUID, recommendation_id: UUID
    ) -> tuple[AssessmentRevision, ...]: ...
    def append(self, revision: AssessmentRevision) -> AssessmentRevision:
        """Append immutable revision after checking recommendation/business/company membership."""
        ...

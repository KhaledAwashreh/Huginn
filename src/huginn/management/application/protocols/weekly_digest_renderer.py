"""Presentation boundary for immutable weekly digest content."""

from datetime import date
from typing import Protocol
from uuid import UUID

from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)
from huginn.management.application.read_models.weekly_digest_message import (
    WeeklyDigestMessage,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision


class WeeklyDigestRenderer(Protocol):
    def render(
        self,
        subscription: DigestSubscription,
        week_start: date,
        content_id: UUID,
        revisions: tuple[AssessmentRevision, ...],
    ) -> WeeklyDigestMessage: ...

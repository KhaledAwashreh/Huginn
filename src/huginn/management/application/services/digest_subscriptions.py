"""Explicit pilot opt-in and opt-out, docs/weekly-digest.md."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from huginn.management.application.protocols.weekly_digest_repository import (
    WeeklyDigestRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol


class DigestSubscriptionService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkProtocol],
        *,
        repository_factory: Callable[[UnitOfWorkProtocol], WeeklyDigestRepository],
    ):
        self._uow = uow_factory
        self._repository = repository_factory

    def subscribe(self, user_id: UUID):
        with self._uow() as work:
            self._repository(work).subscribe(user_id, datetime.now(UTC))
            work.commit()

    def unsubscribe(self, user_id: UUID):
        with self._uow() as work:
            self._repository(work).unsubscribe(user_id)
            work.commit()

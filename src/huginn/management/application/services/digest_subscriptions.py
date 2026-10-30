"""Explicit pilot opt-in and opt-out, docs/weekly-digest.md."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from huginn.management.application.protocols.weekly_digest_repository import (
    WeeklyDigestRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol
from huginn.management.security.digest_unsubscribe import valid_digest_unsubscribe


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

    def unsubscribe_signed(self, user_id: UUID, token: str, signing_key: str) -> bool:
        with self._uow() as work:
            repository = self._repository(work)
            current = repository.subscription(user_id)
            if current is None or not valid_digest_unsubscribe(
                signing_key, user_id, current.recipient, current.version, token
            ):
                return False
            repository.unsubscribe(user_id)
            work.commit()
            return True

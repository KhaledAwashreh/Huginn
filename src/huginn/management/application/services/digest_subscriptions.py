"""Explicit pilot opt-in and opt-out, docs/weekly-digest.md."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from huginn.management.application.protocols.digest_subscription_access import (
    DigestSubscriptionAccess,
)
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.persistence.contracts.repositories.business import (
    BusinessRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol
from huginn.management.security.digest_unsubscribe import valid_digest_unsubscribe


class DigestSubscriptionService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkProtocol],
        *,
        access_factory: Callable[[UnitOfWorkProtocol], DigestSubscriptionAccess],
        businesses_factory: Callable[[UnitOfWorkProtocol], BusinessRepository],
        clock: Callable[[], datetime] | None = None,
    ):
        self._uow = uow_factory
        self._access = access_factory
        self._businesses = businesses_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def _business_id(self, work: UnitOfWorkProtocol, user_id: UUID) -> UUID:
        business = self._businesses(work).get_by_owner_user_id(user_id)
        if business is None:
            raise NotFoundError("Business not found")
        return business.id

    def subscribe(self, user_id: UUID):
        with self._uow() as work:
            business_id = self._business_id(work, user_id)
            self._access(work).subscribe(user_id, business_id, self._clock())
            work.commit()

    def unsubscribe(self, user_id: UUID):
        with self._uow() as work:
            business_id = self._business_id(work, user_id)
            self._access(work).unsubscribe(user_id, business_id, self._clock())
            work.commit()

    def unsubscribe_signed(self, user_id: UUID, token: str, signing_key: str) -> bool:
        with self._uow() as work:
            business = self._businesses(work).get_by_owner_user_id(user_id)
            if business is None:
                return False
            access = self._access(work)
            current = access.get_for_opt_out(business.id)
            if current is None or not valid_digest_unsubscribe(
                signing_key, user_id, current.recipient, current.version, token
            ):
                return False
            access.unsubscribe(user_id, business.id, self._clock())
            work.commit()
            return True

"""Commit bounded, actor-free cleanup of expired Preparing offer claims."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)

_PAGE_SIZE = 100


def release_expired_preparing_offers(
    unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
    business_id: UUID,
    *,
    clock: Callable[[], datetime],
    company_ids: tuple[UUID, ...] | None = None,
    limit: int = _PAGE_SIZE,
) -> int:
    """Release up to 100 expired claims before source/currentness validation.

    Pair locks are acquired in stable Company order and every cycle is reread
    after its lock. Selected Companies can be targeted so a larger Business
    backlog cannot strand an eligible candidate behind the first page. This
    cleanup is actor-free; Sending and Unknown are excluded by the query.
    """

    if not isinstance(business_id, UUID):
        raise ValidationDomainError("Business ID is required for offer cleanup")
    if type(limit) is not int or not 1 <= limit <= _PAGE_SIZE:
        raise ValidationDomainError("Offer cleanup limit must be between 1 and 100")
    if company_ids is not None and (
        type(company_ids) is not tuple
        or len(company_ids) > _PAGE_SIZE
        or any(not isinstance(value, UUID) for value in company_ids)
    ):
        raise ValidationDomainError("Offer cleanup Company scope is invalid")
    if company_ids == ():
        return 0

    page_time = _aware_now(clock)
    with unit_of_work_factory() as work:
        candidates = work.offer_cycles.list_expired_preparing(
            business_id, page_time, limit, company_ids
        )
        released = 0
        for company_id in sorted({value.company_id for value in candidates}, key=str):
            work.lock_business_company(business_id, company_id)
            for candidate in sorted(
                (value for value in candidates if value.company_id == company_id),
                key=lambda value: str(value.id),
            ):
                current = work.offer_cycles.get_owned(
                    business_id, company_id, candidate.id
                )
                now = _aware_now(clock)
                if (
                    current is not None
                    and current.status.value == "preparing"
                    and current.lease_expires_at is not None
                    and current.lease_expires_at <= now
                    and work.offer_cycles.release_expired_preparing(
                        business_id, company_id, current.id, now
                    )
                ):
                    released += 1
        if released:
            work.commit()
        return released


def _aware_now(clock: Callable[[], datetime]) -> datetime:
    now = clock()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValidationDomainError("Offer cleanup clock must include a timezone")
    return now.astimezone(UTC)

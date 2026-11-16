from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from huginn.management.application.services.release_expired_preparing_offers import (
    release_expired_preparing_offers,
)


def test_cleanup_scans_one_bounded_batch_and_leaves_future_work_for_next_request():
    now = datetime(2026, 11, 14, tzinfo=UTC)
    business_id = uuid4()
    company_ids = tuple(sorted((uuid4(), uuid4()), key=str))
    candidates = [
        SimpleNamespace(
            id=uuid4(),
            business_id=business_id,
            company_id=company_ids[index % 2],
            status=SimpleNamespace(value="preparing"),
            lease_expires_at=now - timedelta(minutes=1),
        )
        for index in range(150)
    ]
    scanned = []
    released = set()
    committed = []

    class OfferCycles:
        def list_expired_preparing(
            self, requested_business_id, at, limit, requested_companies
        ):
            assert requested_business_id == business_id
            assert at == now
            assert limit == 100
            assert requested_companies is None
            scanned.append(limit)
            return tuple(item for item in candidates if item.id not in released)[:limit]

        def get_owned(self, requested_business_id, company_id, cycle_id):
            return next(
                (
                    item
                    for item in candidates
                    if item.id == cycle_id
                    and item.company_id == company_id
                    and item.id not in released
                ),
                None,
            )

        def release_expired_preparing(
            self, requested_business_id, company_id, cycle_id, at
        ):
            assert requested_business_id == business_id
            assert at == now
            released.add(cycle_id)
            return True

    class Work:
        offer_cycles = OfferCycles()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def lock_business_company(self, requested_business_id, company_id):
            assert requested_business_id == business_id

        def commit(self):
            committed.append(True)

    def clock():
        return now

    assert release_expired_preparing_offers(Work, business_id, clock=clock) == 100
    assert len(scanned) == 1
    assert len(released) == 100
    assert committed == [True]

    assert release_expired_preparing_offers(Work, business_id, clock=clock) == 50
    assert len(scanned) == 2
    assert len(released) == 150
    assert committed == [True, True]

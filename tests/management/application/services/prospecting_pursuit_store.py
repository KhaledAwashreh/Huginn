"""Transactional in-memory store for manual pursuit command tests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from huginn.management.domain.entities.business import Business
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.prospect_stage import ProspectStage

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


class ProspectingPursuitStore:
    def __init__(self, *, stage: str = "saved") -> None:
        self.principal = Principal(uuid4(), uuid4())
        self.business = Business(
            uuid4(),
            self.principal.user_id,
            None,
            None,
            None,
            None,
            None,
            None,
            NOW,
            NOW,
        )
        self.prospect = Prospect(
            uuid4(),
            self.business.id,
            uuid4(),
            ProspectStage(stage),
            NOW,
            NOW,
            notes="Existing memo",
        )
        self.activities = []
        self.activity_receipts = {}
        self.receipts = {}
        self.commits = 0
        self.fail_receipt = False
        self.after_lock = lambda: None

    def uow(self):
        return MemoryProspectingUow(self)


class MemoryProspectingUow:
    connection = None

    def __init__(self, store: ProspectingPursuitStore) -> None:
        self.store = store
        self.businesses = SimpleNamespace(
            get_by_owner_user_id=lambda user_id: (
                store.business if user_id == store.principal.user_id else None
            )
        )
        self.prospects = SimpleNamespace(
            get_owned=self.get_prospect,
            update_owned=self.update_prospect,
        )
        self.activities = SimpleNamespace(
            list_owned=self.list_activities,
            append_once=self.append_activity,
        )
        self.commands = SimpleNamespace(
            get_by_key=self.get_receipt,
            record=self.record_receipt,
        )

    def __enter__(self):
        self.snapshot = (
            self.store.prospect,
            list(self.store.activities),
            dict(self.store.activity_receipts),
            dict(self.store.receipts),
        )
        self.committed = False
        return self

    def __exit__(self, *_):
        if not self.committed:
            self.rollback()
        return False

    def lock_business_company(self, business_id, company_id) -> None:
        assert (business_id, company_id) == (
            self.store.business.id,
            self.store.prospect.company_id,
        )
        self.store.after_lock()

    def commit(self) -> None:
        self.committed = True
        self.store.commits += 1

    def rollback(self) -> None:
        self.store.prospect = self.snapshot[0]
        self.store.activities[:] = self.snapshot[1]
        self.store.activity_receipts.clear()
        self.store.activity_receipts.update(self.snapshot[2])
        self.store.receipts.clear()
        self.store.receipts.update(self.snapshot[3])

    def get_prospect(self, business_id, prospect_id):
        prospect = self.store.prospect
        return (
            prospect
            if (prospect.business_id, prospect.id) == (business_id, prospect_id)
            else None
        )

    def update_prospect(self, business_id, prospect_id, expected_version, prospect):
        current = self.get_prospect(business_id, prospect_id)
        if current is None:
            from huginn.management.domain.errors.errors import NotFoundError

            raise NotFoundError("Prospect not found")
        if current.version != expected_version:
            raise ConflictError("Prospect changed before the command completed")
        if prospect.version != expected_version + 1:
            raise ConflictError("Prospect update must advance one version")
        self.store.prospect = prospect
        return prospect

    def list_activities(self, business_id, prospect_id):
        if self.get_prospect(business_id, prospect_id) is None:
            return ()
        return tuple(
            sorted(
                (
                    activity
                    for activity in self.store.activities
                    if (activity.business_id, activity.prospect_id)
                    == (business_id, prospect_id)
                ),
                key=lambda activity: (activity.recorded_at, activity.id.int),
            )
        )

    def append_activity(self, business_id, prospect_id, identity, activity):
        if (activity.business_id, activity.prospect_id) != (business_id, prospect_id):
            raise ConflictError("Activity identity is outside this prospect")
        key = (business_id, identity.key)
        if key in self.store.activity_receipts:
            fingerprint, existing = self.store.activity_receipts[key]
            if fingerprint != identity.payload_fingerprint:
                raise ConflictError("Activity key was used for a different payload")
            return existing
        self.store.activity_receipts[key] = (identity.payload_fingerprint, activity)
        self.store.activities.append(activity)
        return activity

    def get_receipt(self, business_id, key):
        return self.store.receipts.get((business_id, key))

    def record_receipt(self, receipt):
        if self.store.fail_receipt:
            raise ConflictError("Simulated receipt failure")
        key = (receipt.business_id, receipt.identity.key)
        if key in self.store.receipts:
            raise ConflictError("Request key already exists")
        self.store.receipts[key] = receipt
        return receipt

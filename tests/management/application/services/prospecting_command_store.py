"""Small transactional fake for recommendation suppression command tests."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from huginn.management.domain.entities.business import Business
from huginn.management.domain.entities.business_recommendation_preferences import (
    BusinessRecommendationPreferences,
)
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.offer_cycle_status import OfferCycleStatus
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


class ProspectingCommandStore:
    def __init__(self) -> None:
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
        self.recommendation = Recommendation(
            uuid4(),
            self.business.id,
            uuid4(),
            RecommendationStatus("open"),
            NOW,
            NOW,
            version=4,
        )
        self.revision = SimpleNamespace(
            id=uuid4(),
            recommendation_id=self.recommendation.id,
            business_id=self.business.id,
            company_id=self.recommendation.company_id,
        )
        self.preferences = BusinessRecommendationPreferences(self.business.id, 30, NOW)
        self.suppression_blocks: list[SuppressionBlock] = []
        self.prospect = None
        self.pending_offer = None
        self.receipts = {}
        self.commits = 0
        self.fail_receipt = False
        self.after_lock = lambda: None

    def block(
        self,
        kind: str,
        *,
        created_at: datetime = NOW,
        expires_at: datetime | None = None,
        business_id=None,
        company_id=None,
        actor_user_id=None,
        reason: str | None = None,
    ) -> SuppressionBlock:
        block = SuppressionBlock(
            id=uuid4(),
            business_id=business_id or self.business.id,
            company_id=company_id or self.recommendation.company_id,
            kind=SuppressionKind(kind),
            created_at=created_at,
            effective_at=created_at,
            created_by_user_id=actor_user_id
            if actor_user_id is not None
            else (self.principal.user_id if kind in {"pause", "rejection"} else None),
            expires_at=expires_at,
            reason=reason,
        )
        self.suppression_blocks.append(block)
        return block

    def uow(self):
        return MemoryProspectingUow(self)


class MemoryProspectingUow:
    connection = None

    def __init__(self, store: ProspectingCommandStore) -> None:
        self.store = store
        self.businesses = SimpleNamespace(
            get_by_owner_user_id=lambda user_id: (
                store.business if user_id == store.principal.user_id else None
            )
        )
        self.business_recommendation_preferences = SimpleNamespace(
            get=lambda business_id: (
                store.preferences if business_id == store.business.id else None
            )
        )
        self.recommendations = SimpleNamespace(
            get_owned=self.get_recommendation,
            resolve_owned=self.resolve_recommendation,
        )
        self.assessment_revisions = SimpleNamespace(get_owned=self.get_revision)
        self.suppression_blocks = SimpleNamespace(
            list_active=self.list_active,
            list_history=self.list_history,
            get_owned=self.get_block,
            append=self.append_block,
            clear_one=self.clear_block,
        )
        self.prospects = SimpleNamespace(get_by_business_company=self.get_prospect)
        self.offer_cycles = SimpleNamespace(get_pending=self.get_pending_offer)
        self.commands = SimpleNamespace(
            get_by_key=self.get_receipt,
            record=self.record_receipt,
        )

    def __enter__(self):
        self.snapshot = (
            self.store.recommendation,
            list(self.store.suppression_blocks),
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
            self.store.recommendation.company_id,
        )
        self.store.after_lock()

    def commit(self) -> None:
        self.committed = True
        self.store.commits += 1

    def rollback(self) -> None:
        recommendation, blocks, receipts = self.snapshot
        self.store.recommendation = recommendation
        self.store.suppression_blocks[:] = blocks
        self.store.receipts.clear()
        self.store.receipts.update(receipts)

    def get_recommendation(self, business_id, recommendation_id):
        recommendation = self.store.recommendation
        return (
            recommendation
            if (recommendation.business_id, recommendation.id)
            == (business_id, recommendation_id)
            else None
        )

    def resolve_recommendation(
        self,
        business_id,
        recommendation_id,
        expected_version,
        status,
        actor_user_id,
        resolved_at,
        reason,
    ):
        recommendation = self.get_recommendation(business_id, recommendation_id)
        if recommendation is None or recommendation.version != expected_version:
            raise ConflictError("Recommendation version changed")
        self.store.recommendation = replace(
            recommendation,
            status=status,
            resolved_at=resolved_at,
            resolved_by_user_id=actor_user_id,
            resolution_reason=reason,
            updated_at=resolved_at,
            version=expected_version + 1,
        )
        return self.store.recommendation

    def get_revision(self, business_id, recommendation_id, revision_id):
        revision = self.store.revision
        return (
            revision
            if (revision.business_id, revision.recommendation_id, revision.id)
            == (business_id, recommendation_id, revision_id)
            else None
        )

    def list_active(self, business_id, company_id, at):
        return tuple(
            block
            for block in self.store.suppression_blocks
            if (block.business_id, block.company_id) == (business_id, company_id)
            and block.is_active_at(at)
        )

    def list_history(self, business_id, company_id):
        return tuple(
            sorted(
                (
                    block
                    for block in self.store.suppression_blocks
                    if (block.business_id, block.company_id)
                    == (business_id, company_id)
                ),
                key=lambda block: (block.created_at, block.id.int),
            )
        )

    def get_block(self, business_id, block_id):
        return next(
            (
                block
                for block in self.store.suppression_blocks
                if (block.business_id, block.id) == (business_id, block_id)
            ),
            None,
        )

    def append_block(self, block):
        self.store.suppression_blocks.append(block)
        return block

    def clear_block(
        self,
        business_id,
        company_id,
        block_id,
        expected_version,
        actor_user_id,
        cleared_at,
    ):
        for index, block in enumerate(self.store.suppression_blocks):
            if (block.business_id, block.company_id, block.id) != (
                business_id,
                company_id,
                block_id,
            ):
                continue
            if block.version != expected_version or block.cleared_at is not None:
                raise ConflictError("Suppression block version changed")
            updated = replace(
                block,
                cleared_at=cleared_at,
                cleared_by_user_id=actor_user_id,
                version=expected_version + 1,
            )
            self.store.suppression_blocks[index] = updated
            return updated
        raise ConflictError("Suppression block is outside this scope")

    def get_prospect(self, business_id, company_id):
        prospect = self.store.prospect
        return (
            prospect
            if prospect is not None
            and (prospect.business_id, prospect.company_id) == (business_id, company_id)
            else None
        )

    def get_pending_offer(self, business_id, company_id):
        offer = self.store.pending_offer
        if offer is None or (offer.business_id, offer.company_id) != (
            business_id,
            company_id,
        ):
            return None
        return offer

    def get_receipt(self, business_id, key):
        return self.store.receipts.get((business_id, key))

    def record_receipt(self, receipt):
        if self.store.fail_receipt:
            raise ConflictError("Concurrent request key belongs to other intent")
        key = (receipt.business_id, receipt.identity.key)
        if key in self.store.receipts:
            raise ConflictError("Request key was already used")
        self.store.receipts[key] = receipt
        return receipt


def pending_offer(store: ProspectingCommandStore, status: str):
    return SimpleNamespace(
        business_id=store.business.id,
        company_id=store.recommendation.company_id,
        status=OfferCycleStatus(status),
    )

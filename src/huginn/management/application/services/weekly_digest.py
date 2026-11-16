"""Authorize and deliver one immutable weekly recommendation digest per Business/week."""

import hashlib
import logging
import secrets
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from huginn.management.application.errors.mail_pre_transport import (
    MailPreTransportError,
)
from huginn.management.application.policies.recommendation_profile_validation import (
    validated_profile_inputs,
)
from huginn.management.application.protocols.digest_subscription_access import (
    DigestSubscriptionAccess,
)
from huginn.management.application.protocols.recommendation_generation import (
    RecommendationGenerationSource,
)
from huginn.management.application.protocols.weekly_digest_renderer import (
    WeeklyDigestRenderer,
)
from huginn.management.application.protocols.weekly_digest_sender import (
    WeeklyDigestSender,
)
from huginn.management.application.protocols.weekly_recommendation_generation import (
    WeeklyRecommendationGeneration,
)
from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)
from huginn.management.application.read_models.generated_recommendation_reference import (
    GeneratedRecommendationReference,
)
from huginn.management.application.read_models.weekly_digest_message import (
    WeeklyDigestMessage,
)
from huginn.management.application.services.recommendation_offer_selection import (
    assert_assessed_after_last_cooldown,
    load_current_offer_selection,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.offer_cycle import OfferCycle
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.entities.weekly_digest_content import WeeklyDigestContent
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.accepted_offer_cadence import (
    AcceptedOfferCadence,
)
from huginn.management.domain.value_objects.offer_cycle_status import OfferCycleStatus
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.domain.value_objects.weekly_digest_member import (
    WeeklyDigestMember,
)
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)
from huginn.management.persistence.contracts.repositories.weekly_digest_content import (
    WeeklyDigestContentRepository,
)
from huginn.management.persistence.contracts.repositories.weekly_digest_delivery import (
    WeeklyDigestDeliveryRepository,
)
from huginn.matchmaking.domain.policies.recommendation_eligibility import (
    assess_recommendation_eligibility,
)

logger = logging.getLogger(__name__)
_DEFAULT_PREPARING_LEASE = timedelta(minutes=5)


class WeeklyDigestService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        subscription_access_factory: Callable[
            [ProspectingUnitOfWork], DigestSubscriptionAccess
        ],
        delivery_repository_factory: Callable[
            [ProspectingUnitOfWork], WeeklyDigestDeliveryRepository
        ],
        content_repository_factory: Callable[
            [ProspectingUnitOfWork], WeeklyDigestContentRepository
        ],
        source_factory: Callable[[DatabaseSession], RecommendationGenerationSource],
        generation: WeeklyRecommendationGeneration,
        renderer: WeeklyDigestRenderer,
        sender: WeeklyDigestSender,
        sender_address: str,
        clock: Callable[[], datetime] | None = None,
        claim_token_factory: Callable[[], str] | None = None,
    ) -> None:
        if not sender_address or "@" not in sender_address:
            raise ValueError("Digest sender address is required")
        self._uow_factory = unit_of_work_factory
        self._subscription_access_factory = subscription_access_factory
        self._delivery_repository = delivery_repository_factory
        self._content_repository = content_repository_factory
        self._source_factory = source_factory
        self._generation = generation
        self._renderer = renderer
        self._sender = sender
        self._sender_domain = sender_address.rsplit("@", 1)[-1]
        self._clock = clock or (lambda: datetime.now(UTC))
        self._claim_token = claim_token_factory or (lambda: secrets.token_urlsafe(32))

    def run(
        self, *, limit: int = 100, daily_limit: int = 100, dry_run: bool = False
    ) -> dict[str, int]:
        if any(
            type(value) is not int or not 1 <= value <= 250
            for value in (limit, daily_limit)
        ):
            raise ValueError("Digest limits must be between one and 250")
        now = self._now()
        week_start = now.date() - timedelta(days=now.weekday())
        with self._uow_factory() as work:
            subscriptions = self._subscription_access(work).list_eligible(limit)
        result = {
            "eligible": len(subscriptions),
            "sent": 0,
            "skipped": 0,
            "empty": 0,
            "unknown": 0,
            "failed": 0,
        }
        if dry_run:
            return result
        for subscription in subscriptions:
            try:
                outcome = self._deliver(subscription, week_start, daily_limit)
            except Exception as error:
                logger.error(
                    "Weekly digest processing failed business=%s error=%s",
                    subscription.business_id,
                    type(error).__name__,
                )
                result["failed"] += 1
                continue
            result[outcome] += 1
        return result

    def _deliver(
        self, subscription: DigestSubscription, week_start: date, daily_limit: int
    ) -> str:
        if not self._has_valid_active_profile(subscription):
            return "skipped"
        with self._uow_factory() as work:
            delivery = self._delivery_repository(work).reserve(
                subscription.business_id,
                subscription.user_id,
                week_start,
                self._now(),
                daily_limit,
            )
            if delivery is None:
                work.commit()
                return "skipped"
            work.commit()

        try:
            generated = self._generation.execute_weekly(subscription.business_id)
            if generated.business_id != subscription.business_id:
                raise ConflictError("Weekly generation returned another Business")
            if not generated.references:
                self._settle_before_send(delivery, "empty")
                return "empty"
            prepared = self._prepare_content(
                subscription, delivery, week_start, generated.references
            )
            if prepared is None:
                return "skipped"
            content, claims = prepared
        except Exception:
            self._settle_before_send(delivery, "preparation_failed")
            raise

        try:
            authorized = self._authorize(subscription, delivery, content, claims)
        except Exception:
            self._cleanup_pre_authorization(delivery, content, claims)
            raise
        if authorized is None:
            return "skipped"
        authorized_delivery, authorized_content, authorized_claims = authorized

        try:
            accepted_at = self._sender.send(_message_from_content(authorized_content))
            accepted_at = _aware_utc(accepted_at)
        except MailPreTransportError:
            self._settle_transport(
                authorized_delivery,
                authorized_content,
                authorized_claims,
                "pre_send_failed",
            )
            return "failed"
        except Exception as error:
            logger.warning(
                "Weekly digest SMTP outcome is uncertain delivery=%s type=%s",
                authorized_delivery.id,
                type(error).__name__,
            )
            self._settle_transport(
                authorized_delivery,
                authorized_content,
                authorized_claims,
                "unknown",
                reason=type(error).__name__,
            )
            return "unknown"

        self._settle_transport(
            authorized_delivery,
            authorized_content,
            authorized_claims,
            "sent",
            accepted_at=accepted_at,
        )
        return "sent"

    def _has_valid_active_profile(self, subscription: DigestSubscription) -> bool:
        with self._uow_factory() as work:
            source = self._source(work)
            profiles = source.active_profiles(subscription.user_id)
            for profile in profiles:
                try:
                    validated_profile_inputs(profile)
                except Exception:
                    continue
                return True
            return False

    def _prepare_content(
        self,
        subscription: DigestSubscription,
        delivery,
        week_start: date,
        references: tuple[GeneratedRecommendationReference, ...],
    ) -> tuple[WeeklyDigestContent, dict[UUID, str]] | None:
        now = self._now()
        claims: dict[UUID, str] = {}
        selected: list[tuple[UUID, UUID, AssessmentRevision]] = []
        with self._uow_factory() as work:
            source = self._source(work)
            candidates = []
            for reference in references:
                recommendation = work.recommendations.get_owned(
                    subscription.business_id, reference.recommendation_id
                )
                revision = work.assessment_revisions.get_owned(
                    subscription.business_id,
                    reference.recommendation_id,
                    reference.revision_id,
                )
                if recommendation is None or revision is None:
                    continue
                if recommendation.current_revision_id != revision.id:
                    continue
                candidates.append((recommendation.company_id, reference, revision))
            for company_id in sorted({item[0] for item in candidates}, key=str):
                work.lock_business_company(subscription.business_id, company_id)
            for company_id, reference, _revision in candidates:
                try:
                    selection = load_current_offer_selection(
                        work,
                        source,
                        subscription.business_id,
                        subscription.user_id,
                        reference.recommendation_id,
                        reference.revision_id,
                        now,
                    )
                    assert_assessed_after_last_cooldown(
                        work,
                        subscription.business_id,
                        company_id,
                        selection.revision.assessed_at,
                    )
                    states = source.company_states(
                        subscription.business_id, (company_id,), now
                    )
                    if (
                        len(states) != 1
                        or not assess_recommendation_eligibility(
                            states[0], now
                        ).eligible
                    ):
                        continue
                    if (
                        work.offer_cycles.get_pending(
                            subscription.business_id, company_id
                        )
                        is not None
                    ):
                        continue
                except Exception:
                    continue
                claim_token = self._claim_token()
                cycle_id = uuid4()
                request_key = f"weekly-digest:{delivery.id}:{company_id}"
                fingerprint = hashlib.sha256(
                    f"{subscription.business_id}:{delivery.id}:{company_id}:"
                    f"{reference.recommendation_id}:{reference.revision_id}".encode()
                ).hexdigest()
                cycle = OfferCycle(
                    cycle_id,
                    subscription.business_id,
                    company_id,
                    reference.recommendation_id,
                    reference.revision_id,
                    request_key,
                    fingerprint,
                    OfferCycleStatus("preparing"),
                    now,
                    now,
                    claim_token,
                    now + _DEFAULT_PREPARING_LEASE,
                )
                work.offer_cycles.acquire_preparing(
                    cycle,
                    now=now,
                    lease_expires_at=now + _DEFAULT_PREPARING_LEASE,
                    claim_token=claim_token,
                )
                claims[cycle_id] = claim_token
                selected.append((company_id, cycle_id, selection.revision))
            if not selected:
                self._delivery_repository(work).settle(
                    subscription.business_id,
                    delivery.id,
                    delivery.version,
                    "suppressed",
                    self._now(),
                )
                work.commit()
                return None
            content = self._new_content(
                subscription,
                delivery.id,
                1,
                week_start,
                tuple(item[2] for item in selected),
                tuple((item[0], item[1], item[2]) for item in selected),
            )
            content_repo = self._content_repository(work)
            delivery_repo = self._delivery_repository(work)
            content_repo.append(content)
            delivery_repo.select_content(
                subscription.business_id,
                delivery.id,
                delivery.version,
                content.id,
                self._now(),
            )
            work.commit()
        return content, claims

    def _new_content(
        self,
        subscription: DigestSubscription,
        delivery_id: UUID,
        version: int,
        week_start: date,
        revisions: tuple[AssessmentRevision, ...],
        selected: tuple[tuple[UUID, UUID, AssessmentRevision], ...],
    ) -> WeeklyDigestContent:
        content_id = uuid4()
        message = self._renderer.render(subscription, week_start, content_id, revisions)

        members = tuple(
            WeeklyDigestMember(
                company_id,
                revision.recommendation_id,
                revision.id,
                cycle_id,
                position,
            )
            for position, (company_id, cycle_id, revision) in enumerate(selected, 1)
        )
        return WeeklyDigestContent(
            content_id,
            delivery_id,
            subscription.business_id,
            subscription.user_id,
            version,
            self._now(),
            subscription.updated_at,
            subscription.recipient,
            message.subject,
            message.body,
            message.message_id,
            members,
        )

    def _authorize(self, subscription, delivery, content, claims):
        with self._uow_factory() as work:
            current_subscription = self._subscription_access(
                work
            ).get_for_authorization(subscription.business_id)
            current_delivery = self._delivery_repository(work).get_for_update(
                subscription.business_id, delivery.id
            )
            members = content.members
            for company_id in sorted(
                {member.company_id for member in members}, key=str
            ):
                work.lock_business_company(subscription.business_id, company_id)
            if (
                current_subscription is None
                or current_delivery is None
                or current_subscription.user_id != subscription.user_id
                or current_subscription.recipient != subscription.recipient
                or current_subscription.updated_at != subscription.updated_at
                or current_delivery.current_content_id != content.id
                or current_delivery.state != "preparing"
            ):
                for member in members:
                    cycle = work.offer_cycles.get_owned(
                        subscription.business_id,
                        member.company_id,
                        member.offer_cycle_id,
                    )
                    token = claims.get(member.offer_cycle_id)
                    if (
                        cycle is not None
                        and cycle.status.value == "preparing"
                        and token is not None
                    ):
                        work.offer_cycles.abandon_preparing(
                            subscription.business_id,
                            member.company_id,
                            member.offer_cycle_id,
                            token,
                            None,
                            "Weekly delivery authorization inputs changed",
                            self._now(),
                        )
                if (
                    current_delivery is not None
                    and current_delivery.state == "preparing"
                ):
                    self._delivery_repository(work).settle(
                        subscription.business_id,
                        delivery.id,
                        current_delivery.version,
                        "suppressed",
                        self._now(),
                    )
                work.commit()
                return None
            source = self._source(work)
            valid = []
            for member in members:
                token = claims.get(member.offer_cycle_id)
                cycle = work.offer_cycles.get_owned(
                    subscription.business_id, member.company_id, member.offer_cycle_id
                )
                if (
                    token is None
                    or cycle is None
                    or cycle.status.value != "preparing"
                    or cycle.claim_token != token
                ):
                    continue
                try:
                    selection = load_current_offer_selection(
                        work,
                        source,
                        subscription.business_id,
                        subscription.user_id,
                        member.recommendation_id,
                        member.assessment_revision_id,
                        self._now(),
                    )
                    assert_assessed_after_last_cooldown(
                        work,
                        subscription.business_id,
                        member.company_id,
                        selection.revision.assessed_at,
                    )
                    state = source.company_states(
                        subscription.business_id,
                        (member.company_id,),
                        self._now(),
                        exclude_offer_cycle_id=member.offer_cycle_id,
                    )
                    if (
                        len(state) != 1
                        or not assess_recommendation_eligibility(
                            state[0], self._now()
                        ).eligible
                    ):
                        continue
                except Exception:
                    continue
                valid.append((member, cycle, selection.revision, token))

            for member in members:
                if not any(
                    value[0].offer_cycle_id == member.offer_cycle_id for value in valid
                ):
                    cycle = work.offer_cycles.get_owned(
                        subscription.business_id,
                        member.company_id,
                        member.offer_cycle_id,
                    )
                    token = claims.get(member.offer_cycle_id)
                    if (
                        cycle is not None
                        and cycle.status.value == "preparing"
                        and token
                    ):
                        work.offer_cycles.abandon_preparing(
                            subscription.business_id,
                            member.company_id,
                            member.offer_cycle_id,
                            token,
                            None,
                            "Weekly selection changed before authorization",
                            self._now(),
                        )
            if not valid:
                self._delivery_repository(work).settle(
                    subscription.business_id,
                    delivery.id,
                    current_delivery.version,
                    "suppressed",
                    self._now(),
                )
                work.commit()
                return None

            replacement_content = content
            if len(valid) != len(members):
                replacement_content = self._new_content(
                    current_subscription,
                    delivery.id,
                    content.version + 1,
                    delivery.week_start,
                    tuple(value[2] for value in valid),
                    tuple(
                        (value[0].company_id, value[0].offer_cycle_id, value[2])
                        for value in valid
                    ),
                )
                self._content_repository(work).append(replacement_content)
                current_delivery = self._delivery_repository(work).select_content(
                    subscription.business_id,
                    delivery.id,
                    current_delivery.version,
                    replacement_content.id,
                    self._now(),
                )
            preferences = work.business_recommendation_preferences.get(
                subscription.business_id
            )
            if preferences is None:
                raise NotFoundError("Business recommendation preferences not found")
            accepted_cadence_by_cycle = {}
            for member, _cycle, _, token in valid:
                authorized_at = self._now()
                accepted_cadence = AcceptedOfferCadence(
                    preferences.repeat_interval_days,
                    preferences.updated_at,
                    authorized_at,
                )
                work.offer_cycles.mark_sending(
                    subscription.business_id,
                    member.company_id,
                    member.offer_cycle_id,
                    token,
                    authorized_at,
                    accepted_cadence,
                )
                accepted_cadence_by_cycle[member.offer_cycle_id] = accepted_cadence
            sending_delivery = self._delivery_repository(work).authorize_sending(
                subscription.business_id,
                delivery.id,
                current_delivery.version,
                replacement_content.id,
                self._now(),
            )
            work.commit()
            return (
                sending_delivery,
                replacement_content,
                {
                    cycle_id: (token, accepted_cadence_by_cycle[cycle_id])
                    for _, cycle, _, token in valid
                    for cycle_id in (cycle.id,)
                },
            )

    def _settle_transport(
        self,
        delivery,
        content: WeeklyDigestContent,
        claims: dict[UUID, tuple[str, AcceptedOfferCadence]],
        outcome: str,
        *,
        accepted_at: datetime | None = None,
        reason: str | None = None,
    ) -> None:
        now = self._now()
        with self._uow_factory() as work:
            for company_id in sorted(
                {member.company_id for member in content.members}, key=str
            ):
                work.lock_business_company(content.business_id, company_id)
            for member in content.members:
                claim = claims.get(member.offer_cycle_id)
                if claim is None:
                    raise ConflictError("Authorized weekly claim is missing")
                token, cadence = claim
                if outcome == "sent":
                    actual = accepted_at
                    if actual is None:
                        raise ValueError("SMTP acceptance timestamp is required")
                    work.offer_cycles.settle_sending(
                        content.business_id,
                        member.company_id,
                        member.offer_cycle_id,
                        token,
                        "confirmed",
                        now,
                        actual,
                    )
                    work.recommendations.record_confirmed_presentation(
                        content.business_id,
                        member.company_id,
                        member.recommendation_id,
                        member.offer_cycle_id,
                        member.assessment_revision_id,
                        actual,
                    )
                    work.suppression_blocks.append(
                        SuppressionBlock(
                            uuid4(),
                            content.business_id,
                            member.company_id,
                            SuppressionKind("cooldown"),
                            now,
                            effective_at=actual,
                            expires_at=actual
                            + timedelta(days=cadence.repeat_interval_days),
                        )
                    )
                elif outcome in {"unknown", "pre_send_failed"}:
                    work.offer_cycles.settle_sending(
                        content.business_id,
                        member.company_id,
                        member.offer_cycle_id,
                        token,
                        outcome,
                        now,
                    )
            self._delivery_repository(work).settle(
                content.business_id,
                delivery.id,
                delivery.version,
                outcome,
                now,
                accepted_at,
                reason,
            )
            work.commit()

    def _settle_before_send(self, delivery, outcome: str) -> None:
        with self._uow_factory() as work:
            current = self._delivery_repository(work).get_for_update(
                delivery.business_id, delivery.id
            )
            if current is not None and current.state == "preparing":
                self._delivery_repository(work).settle(
                    delivery.business_id,
                    delivery.id,
                    current.version,
                    outcome,
                    self._now(),
                )
            work.commit()

    def _cleanup_pre_authorization(self, delivery, content, claims) -> None:
        with self._uow_factory() as work:
            for company_id in sorted(
                {member.company_id for member in content.members}, key=str
            ):
                work.lock_business_company(content.business_id, company_id)
            for member in content.members:
                cycle = work.offer_cycles.get_owned(
                    content.business_id, member.company_id, member.offer_cycle_id
                )
                token = claims.get(member.offer_cycle_id)
                if (
                    cycle is not None
                    and cycle.status.value == "preparing"
                    and token is not None
                ):
                    work.offer_cycles.abandon_preparing(
                        content.business_id,
                        member.company_id,
                        member.offer_cycle_id,
                        token,
                        None,
                        "Weekly delivery authorization could not be completed",
                        self._now(),
                    )
            current = self._delivery_repository(work).get_for_update(
                delivery.business_id, delivery.id
            )
            if current is not None and current.state == "preparing":
                self._delivery_repository(work).settle(
                    delivery.business_id,
                    delivery.id,
                    current.version,
                    "preparation_failed",
                    self._now(),
                )
            work.commit()

    def _source(self, work: ProspectingUnitOfWork) -> RecommendationGenerationSource:
        if work.connection is None:
            raise RuntimeError("Weekly digest UOW has no connection")
        return self._source_factory(work.connection)

    def _subscription_access(
        self, work: ProspectingUnitOfWork
    ) -> DigestSubscriptionAccess:
        return self._subscription_access_factory(work)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Weekly digest clock must include a timezone")
        return value.astimezone(UTC)


def _message_from_content(content: WeeklyDigestContent) -> WeeklyDigestMessage:
    return WeeklyDigestMessage(
        content.recipient, content.subject, content.body, content.message_id
    )


def _aware_utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("SMTP acceptance time must include a timezone")
    return value.astimezone(UTC)

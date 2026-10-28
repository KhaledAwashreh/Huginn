"""Small explicit weekly job with durable pre-send reservation; weekly-digest.md."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from huginn.management.application.policies.weekly_digest_content import (
    weekly_digest_body,
)
from huginn.management.application.protocols.weekly_digest_repository import (
    WeeklyDigestRepository,
)
from huginn.management.application.protocols.weekly_digest_sender import (
    WeeklyDigestSender,
)
from huginn.management.application.read_models.weekly_digest_message import (
    WeeklyDigestMessage,
)
from huginn.management.application.services.recommendations import RecommendationService
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol
from huginn.management.security.digest_unsubscribe import digest_unsubscribe_token

logger = logging.getLogger(__name__)


class WeeklyDigestService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        repository_factory: Callable[[UnitOfWorkProtocol], WeeklyDigestRepository],
        recommendations: RecommendationService,
        sender: WeeklyDigestSender,
        web_origin: str,
        sender_address: str,
        signing_key: str,
        clock: Callable[[], datetime] | None = None,
    ):
        if not web_origin or not signing_key:
            raise ValueError("Trusted web origin and digest signing key are required")
        self._uow = unit_of_work_factory
        self._repository = repository_factory
        self._recommendations = recommendations
        self._sender = sender
        self._origin = web_origin.rstrip("/")
        self._domain = sender_address.rsplit("@", 1)[-1]
        self._key = signing_key
        self._clock = clock or (lambda: datetime.now(UTC))

    def _settle(self, delivery_id, state):
        with self._uow() as work:
            self._repository(work).settle(delivery_id, state, self._clock())
            work.commit()

    def run(
        self, *, limit: int = 100, daily_limit: int = 100, dry_run: bool = False
    ) -> dict:
        if any(
            type(value) is not int or not 1 <= value <= 250
            for value in (limit, daily_limit)
        ):
            raise ValueError("Digest limits must be between one and 250")
        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("Digest clock must be timezone-aware")
        now = now.astimezone(UTC)
        week = now.date() - timedelta(days=now.weekday())
        with self._uow() as work:
            subscriptions = self._repository(work).subscriptions(limit)
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
        logger.info("Weekly digest run started, subscriptions=%s", len(subscriptions))
        for subscription in subscriptions:
            with self._uow() as work:
                repository = self._repository(work)
                delivery_id = repository.reserve(
                    subscription.user_id,
                    week,
                    self._clock().astimezone(UTC),
                    daily_limit,
                )
                previous = (
                    repository.previous_companies(subscription.user_id)
                    if delivery_id is not None
                    else frozenset()
                )
                work.commit()
            if delivery_id is None:
                result["skipped"] += 1
                continue
            try:
                batch = self._recommendations.generate_weekly(
                    subscription.user_id,
                    exclude_company_ids=previous,
                )
                if not batch["items"]:
                    self._settle(delivery_id, "empty")
                    result["empty"] += 1
                    continue
                subject = f"Huginn: your Weekly Matches ({week.isoformat()})"
                token = digest_unsubscribe_token(self._key, subscription.user_id)
                batch_url = f"{self._origin}/weekly-matches?batch={batch['id']}"
                unsubscribe_url = f"{self._origin}/weekly-digest/unsubscribe#user_id={subscription.user_id}&token={token}"
                body = weekly_digest_body(batch, week, batch_url, unsubscribe_url)
                message = WeeklyDigestMessage(
                    subscription.recipient,
                    subject,
                    body,
                    f"<weekly-{delivery_id}@{self._domain}>",
                )
                with self._uow() as work:
                    repository = self._repository(work)
                    if not repository.eligible(subscription):
                        repository.settle(delivery_id, "suppressed", self._clock())
                        work.commit()
                        result["skipped"] += 1
                        continue
                    repository.prepare(
                        delivery_id,
                        UUID(batch["id"]),
                        subscription.recipient,
                        subject,
                        body,
                        tuple(UUID(item["company"]["id"]) for item in batch["items"]),
                    )
                    work.commit()
            except Exception as error:
                logger.error(
                    "Digest preparation failed, delivery_id=%s type=%s",
                    delivery_id,
                    type(error).__name__,
                )
                self._settle(delivery_id, "failed")
                result["failed"] += 1
                continue
            try:
                self._sender.send(message)
            except Exception:
                # SMTP acceptance can be uncertain; never automatically resend this week.
                self._settle(delivery_id, "unknown")
                result["unknown"] += 1
                logger.warning(
                    "Digest transport outcome uncertain, delivery_id=%s", delivery_id
                )
                continue
            self._settle(delivery_id, "sent")
            result["sent"] += 1
        logger.info(
            "Weekly digest run completed, sent=%s unknown=%s",
            result["sent"],
            result["unknown"],
        )
        return result

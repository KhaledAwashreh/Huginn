"""Composition for the explicit weekly cron command; no startup IO."""

from huginn.management.application.services.digest_subscriptions import (
    DigestSubscriptionService,
)
from huginn.management.application.services.recommendation_generation import (
    RecommendationGenerationService,
)
from huginn.management.application.services.weekly_digest import WeeklyDigestService
from huginn.management.config import ManagementConfig
from huginn.management.delivery.smtp_digest_mail_sender import SmtpDigestMailSender
from huginn.management.delivery.templates.weekly_digest import (
    PlainTextWeeklyDigestRenderer,
)
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.repositories.business import (
    PostgresBusinessRepository,
)
from huginn.management.persistence.repositories.digest_subscription_access import (
    PostgresDigestSubscriptionAccess,
)
from huginn.management.persistence.repositories.recommendation_generation import (
    PostgresRecommendationGenerationSource,
)
from huginn.management.persistence.repositories.weekly_digest_content import (
    PostgresWeeklyDigestContentRepository,
)
from huginn.management.persistence.repositories.weekly_digest_delivery import (
    PostgresWeeklyDigestDeliveryRepository,
)


def create_digest_subscription_service(
    config: ManagementConfig,
) -> DigestSubscriptionService:
    factory = ManagementConnectionFactory(config.database_url)
    return DigestSubscriptionService(
        lambda: UnitOfWork(factory),
        access_factory=lambda work: PostgresDigestSubscriptionAccess(work.connection),
        businesses_factory=lambda work: PostgresBusinessRepository(work.connection),
    )


def create_weekly_digest_service(config: ManagementConfig) -> WeeklyDigestService:
    if not config.discovery_new_work_enabled:
        raise ValueError("New discovery work is disabled")
    if config.environment in {"production", "staging"} and config.smtp_tls == "none":
        raise ValueError("Production digest SMTP requires TLS")
    if not config.web_origin or not config.lifecycle_proof_key:
        raise ValueError(
            "Trusted web origin and existing application signing key are required"
        )
    factory = ManagementConnectionFactory(config.database_url)

    def make_work():
        return PostgresProspectingUnitOfWork(factory)

    generation = RecommendationGenerationService(
        make_work,
        simple_discovery_enabled=config.simple_discovery_enabled,
        source_factory=PostgresRecommendationGenerationSource,
    )
    return WeeklyDigestService(
        make_work,
        simple_discovery_enabled=config.simple_discovery_enabled,
        subscription_access_factory=lambda work: PostgresDigestSubscriptionAccess(
            work.connection
        ),
        delivery_repository_factory=lambda work: PostgresWeeklyDigestDeliveryRepository(
            work.connection
        ),
        content_repository_factory=lambda work: PostgresWeeklyDigestContentRepository(
            work.connection
        ),
        source_factory=PostgresRecommendationGenerationSource,
        generation=generation,
        renderer=PlainTextWeeklyDigestRenderer(
            config.web_origin,
            config.lifecycle_proof_key,
            config.smtp_sender.rsplit("@", 1)[-1],
        ),
        sender=SmtpDigestMailSender(config),
        sender_address=config.smtp_sender,
    )

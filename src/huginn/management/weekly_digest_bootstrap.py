"""Composition for the explicit weekly cron command; no startup IO."""

from huginn.management.application.services.digest_subscriptions import (
    DigestSubscriptionService,
)
from huginn.management.application.services.recommendations import RecommendationService
from huginn.management.application.services.weekly_digest import WeeklyDigestService
from huginn.management.config import ManagementConfig
from huginn.management.delivery.smtp_digest_mail_sender import SmtpDigestMailSender
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.repositories.recommendations import (
    PostgresRecommendationRepository,
)
from huginn.management.persistence.repositories.weekly_digest import (
    PostgresWeeklyDigestRepository,
)


def create_digest_subscription_service(
    config: ManagementConfig,
) -> DigestSubscriptionService:
    factory = ManagementConnectionFactory(config.database_url)
    return DigestSubscriptionService(
        lambda: UnitOfWork(factory),
        repository_factory=lambda work: PostgresWeeklyDigestRepository(work.connection),
    )


def create_weekly_digest_service(config: ManagementConfig) -> WeeklyDigestService:
    if config.environment in {"production", "staging"} and config.smtp_tls == "none":
        raise ValueError("Production digest SMTP requires TLS")
    if not config.web_origin or not config.lifecycle_proof_key:
        raise ValueError(
            "Trusted web origin and existing application signing key are required"
        )
    factory = ManagementConnectionFactory(config.database_url)

    def make_work():
        return UnitOfWork(factory)

    recommendations = RecommendationService(
        make_work,
        repository_factory=lambda work: PostgresRecommendationRepository(
            work.connection
        ),
    )
    return WeeklyDigestService(
        make_work,
        repository_factory=lambda work: PostgresWeeklyDigestRepository(work.connection),
        recommendations=recommendations,
        sender=SmtpDigestMailSender(config),
        web_origin=config.web_origin,
        sender_address=config.smtp_sender,
        signing_key=config.lifecycle_proof_key,
    )

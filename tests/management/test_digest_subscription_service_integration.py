"""Owner opt-out stays available independently of current matching eligibility."""

from datetime import UTC, datetime
from uuid import uuid4

import psycopg

from huginn.management.application.services.digest_subscriptions import (
    DigestSubscriptionService,
)
from huginn.management.persistence.database.client import (
    ManagementConnectionFactory,
    PsycopgDatabaseSession,
)
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.repositories.business import (
    PostgresBusinessRepository,
)
from huginn.management.persistence.repositories.digest_subscription_access import (
    PostgresDigestSubscriptionAccess,
)
from huginn.management.security.digest_unsubscribe import digest_unsubscribe_token
from tests.management.persistence.digest_subscription_fixtures import (
    seed_digest_subscriber,
)


def test_signed_opt_out_survives_inactive_strategy_and_disabled_account(
    management_database_url,
):
    now = datetime.now(UTC)
    with psycopg.connect(management_database_url) as connection:
        user, account, strategy = seed_digest_subscriber(
            connection, "opt-out-eligibility"
        )
        business = connection.execute(
            "SELECT id FROM operational.businesses WHERE owner_user_id=%s", (user,)
        ).fetchone()[0]
        access = PostgresDigestSubscriptionAccess(connection)
        access.subscribe(user, business, now)
        current = access.get_for_business(business)
        token = digest_unsubscribe_token(
            "test-key", user, current.recipient, current.version
        )
        connection.execute(
            "UPDATE operational.client_discovery_strategies SET is_active=false WHERE id=%s",
            (strategy,),
        )
        connection.execute(
            "UPDATE operational.accounts SET status='disabled' WHERE id=%s", (account,)
        )
    factory = ManagementConnectionFactory(management_database_url)
    service = DigestSubscriptionService(
        lambda: UnitOfWork(factory),
        access_factory=lambda work: PostgresDigestSubscriptionAccess(work.connection),
        businesses_factory=lambda work: PostgresBusinessRepository(work.connection),
    )
    assert service.unsubscribe_signed(user, token, "test-key") is True
    with psycopg.connect(management_database_url) as connection:
        assert (
            connection.execute(
                "SELECT enabled FROM operational.weekly_digest_subscriptions WHERE business_id=%s",
                (business,),
            ).fetchone()[0]
            is False
        )


def test_old_unsubscribe_links_fail_after_recipient_change_or_resubscription(
    management_database_url,
):
    from huginn.management.application.services.digest_subscriptions import (
        DigestSubscriptionService,
    )
    from huginn.management.persistence.database.client import (
        ManagementConnectionFactory,
    )
    from huginn.management.persistence.database.unit_of_work import UnitOfWork
    from huginn.management.security.digest_unsubscribe import digest_unsubscribe_token

    now = datetime.now(UTC)
    key = "test-signing-key"
    with psycopg.connect(management_database_url) as conn:
        repo = PostgresDigestSubscriptionAccess(PsycopgDatabaseSession(conn))
        user, account, _ = seed_digest_subscriber(conn, "recipient-binding")
        business = conn.execute(
            "SELECT id FROM operational.businesses WHERE owner_user_id=%s", (user,)
        ).fetchone()[0]
        repo.subscribe(user, business, now)
        current = repo.get_for_business(business)
        old = digest_unsubscribe_token(key, user, current.recipient, current.version)
        conn.commit()
    factory = ManagementConnectionFactory(management_database_url)
    service = DigestSubscriptionService(
        lambda: UnitOfWork(factory),
        access_factory=lambda work: PostgresDigestSubscriptionAccess(work.connection),
        businesses_factory=lambda work: PostgresBusinessRepository(work.connection),
    )
    with psycopg.connect(management_database_url) as conn:
        conn.execute(
            "UPDATE operational.account_recovery_identity SET verified_email=%s WHERE account_id=%s",
            (f"{uuid4()}@example.test", account),
        )
    assert not service.unsubscribe_signed(user, old, key)
    with psycopg.connect(management_database_url) as conn:
        repo = PostgresDigestSubscriptionAccess(PsycopgDatabaseSession(conn))
        current = repo.get_for_business(business)
        before_resubscribe = digest_unsubscribe_token(
            key, user, current.recipient, current.version
        )
        repo.subscribe(user, business, now)
    assert not service.unsubscribe_signed(user, before_resubscribe, key)
    with psycopg.connect(management_database_url) as conn:
        current = PostgresDigestSubscriptionAccess(
            PsycopgDatabaseSession(conn)
        ).get_for_business(business)
        valid = digest_unsubscribe_token(key, user, current.recipient, current.version)
    assert service.unsubscribe_signed(user, valid, key)
    with psycopg.connect(management_database_url) as conn:
        business = conn.execute(
            "SELECT id FROM operational.businesses WHERE owner_user_id=%s", (user,)
        ).fetchone()[0]
        assert conn.execute(
            "SELECT enabled FROM operational.weekly_digest_subscriptions WHERE business_id=%s",
            (business,),
        ).fetchone() == (False,)

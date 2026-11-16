from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.digest_subscription_access import (
    PostgresDigestSubscriptionAccess,
)
from tests.management.test_matches_query_integration import _user


def _setup(conn):
    conn.execute(Path("db/schema/operational-recommendations.sql").read_text())
    conn.execute(Path("db/schema/operational-weekly-digest.sql").read_text())
    return PostgresDigestSubscriptionAccess(PsycopgDatabaseSession(conn))


def _eligible_owner(conn, tag):
    user_id, account_id = _user(conn, tag)
    business_id = conn.execute(
        "INSERT INTO operational.businesses(owner_user_id) VALUES (%s) RETURNING id",
        (user_id,),
    ).fetchone()[0]
    email = f"{uuid4()}@example.test"
    conn.execute(
        "INSERT INTO operational.account_recovery_identity "
        "(account_id,verification_required,verified_email,verified_at) "
        "VALUES (%s,true,%s,now())",
        (account_id, email),
    )
    offering_id = conn.execute(
        "INSERT INTO operational.service_offerings "
        "(business_id,name,description) VALUES (%s,'Research','Market research') "
        "RETURNING id",
        (business_id,),
    ).fetchone()[0]
    icp_id = conn.execute(
        "INSERT INTO operational.ideal_client_profiles "
        "(business_id,name) VALUES (%s,'Early companies') RETURNING id",
        (business_id,),
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO operational.client_discovery_strategies "
        "(business_id,name,service_offering_id,ideal_client_profile_id,is_active) "
        "VALUES (%s,'Weekly research',%s,%s,true)",
        (business_id, offering_id, icp_id),
    )
    return user_id, account_id, business_id, email


def test_subscription_projection_and_authorization_use_business_owned_verified_state(
    management_database_url,
):
    with psycopg.connect(management_database_url) as conn:
        repository = _setup(conn)
        user_id, _account_id, business_id, email = _eligible_owner(
            conn, "digest-access"
        )
        now = datetime(2045, 5, 7, 12, tzinfo=UTC)
        repository.subscribe(user_id, business_id, now)

        listed = repository.list_eligible(100)
        assert len(listed) == 1
        subscription = listed[0]
        assert subscription.business_id == business_id
        assert subscription.user_id == user_id
        assert subscription.recipient == email
        assert subscription.updated_at == now
        assert subscription.version == now.isoformat()
        assert email not in repr(subscription)
        assert repository.get_for_business(business_id) == subscription
        assert repository.get_for_authorization(business_id) == subscription
        assert conn.execute(
            "SELECT d.business_id,b.owner_user_id,d.enabled,r.verified_email,d.updated_at "
            "FROM operational.weekly_digest_subscriptions d "
            "JOIN operational.businesses b ON b.id=d.business_id "
            "JOIN operational.users u ON u.id=b.owner_user_id "
            "JOIN operational.account_recovery_identity r ON r.account_id=u.account_id "
            "WHERE d.business_id=%s",
            (business_id,),
        ).fetchone() == (business_id, user_id, True, email, now)

        conn.execute(
            "UPDATE operational.accounts SET status='disabled' "
            "WHERE id=(SELECT account_id FROM operational.users WHERE id=%s)",
            (user_id,),
        )
        assert repository.list_eligible(100) == ()
        assert repository.get_for_authorization(business_id) is None
        conn.rollback()


def test_subscription_commands_enforce_owner_and_advance_consent_version(
    management_database_url,
):
    with psycopg.connect(management_database_url) as conn:
        repository = _setup(conn)
        user_id, _account_id, business_id, _email = _eligible_owner(
            conn, "digest-owner"
        )
        other_user_id, _other_account, _other_business, _ = _eligible_owner(
            conn, "digest-foreign"
        )
        now = datetime(2046, 6, 8, 9, tzinfo=UTC)
        repository.subscribe(user_id, business_id, now)
        first = repository.get_for_business(business_id)
        assert first is not None

        with pytest.raises(ValidationDomainError):
            repository.unsubscribe(
                other_user_id, business_id, now + timedelta(seconds=1)
            )
        assert repository.get_for_business(business_id) == first

        repository.unsubscribe(user_id, business_id, now + timedelta(seconds=1))
        assert repository.get_for_business(business_id) is None
        repository.subscribe(user_id, business_id, now)
        renewed = repository.get_for_business(business_id)
        assert renewed is not None
        assert renewed.updated_at > first.updated_at
        assert renewed.version == renewed.updated_at.isoformat()
        conn.rollback()


def test_subscribe_requires_verified_active_account_and_active_owned_strategy(
    management_database_url,
):
    with psycopg.connect(management_database_url) as conn:
        repository = _setup(conn)
        user_id, account_id, business_id, _email = _eligible_owner(
            conn, "digest-ineligible"
        )
        now = datetime(2047, 7, 9, 10, tzinfo=UTC)
        conn.execute(
            "UPDATE operational.account_recovery_identity "
            "SET pending_email=%s,verified_email=NULL,verified_at=NULL "
            "WHERE account_id=%s",
            (f"pending-{uuid4()}@example.test", account_id),
        )
        with pytest.raises(ValidationDomainError):
            repository.subscribe(user_id, business_id, now)
        assert repository.list_eligible(100) == ()
        conn.execute(
            "UPDATE operational.account_recovery_identity "
            "SET pending_email=NULL,verified_email=%s,verified_at=now() "
            "WHERE account_id=%s",
            (f"{uuid4()}@example.test", account_id),
        )
        conn.execute(
            "UPDATE operational.client_discovery_strategies SET is_active=false "
            "WHERE business_id=%s",
            (business_id,),
        )
        with pytest.raises(ValidationDomainError):
            repository.subscribe(user_id, business_id, now)
        conn.execute(
            "UPDATE operational.client_discovery_strategies SET is_active=true "
            "WHERE business_id=%s",
            (business_id,),
        )
        conn.execute(
            "UPDATE operational.accounts SET status='disabled' WHERE id=%s",
            (account_id,),
        )
        with pytest.raises(ValidationDomainError):
            repository.subscribe(user_id, business_id, now)
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.weekly_digest_subscriptions "
                "WHERE business_id=%s",
                (business_id,),
            ).fetchone()[0]
            == 0
        )
        conn.rollback()

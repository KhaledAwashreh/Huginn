from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from huginn.management.application.read_models.digest_subscription import (
    DigestSubscription,
)
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.weekly_digest import (
    PostgresWeeklyDigestRepository,
)
from tests.management.test_matches_query_integration import _user


def _subscriber(conn, tag):
    user, account = _user(conn, tag)
    conn.execute(
        "INSERT INTO operational.account_recovery_identity(account_id,verification_required,verified_email,verified_at) VALUES (%s,true,%s,now())",
        (account, f"{uuid4()}@example.test"),
    )
    offering = conn.execute(
        "INSERT INTO operational.service_offerings(user_id,name,description) VALUES (%s,'Analytics','Reporting') RETURNING id",
        (user,),
    ).fetchone()[0]
    icp = conn.execute(
        "INSERT INTO operational.ideal_client_profiles(user_id,name) VALUES (%s,'Startups') RETURNING id",
        (user,),
    ).fetchone()[0]
    strategy = conn.execute(
        "INSERT INTO operational.client_discovery_strategies(user_id,name,service_offering_id,ideal_client_profile_id,is_active) VALUES (%s,'Weekly',%s,%s,true) RETURNING id",
        (user, offering, icp),
    ).fetchone()[0]
    return user, account, strategy


def _setup(conn):
    conn.execute(Path("db/schema/operational-recommendations.sql").read_text())
    conn.execute(Path("db/schema/operational-weekly-digest.sql").read_text())
    return PostgresWeeklyDigestRepository(PsycopgDatabaseSession(conn))


def test_verified_opt_in_and_current_eligibility(management_database_url):
    with psycopg.connect(management_database_url) as conn:
        repo = _setup(conn)
        user, account, strategy = _subscriber(conn, "weekly")
        now = datetime.now(UTC)
        assert repo.subscriptions(100) == ()
        repo.subscribe(user, strategy, now)
        subscription = repo.subscriptions(100)[0]
        assert subscription.user_id == user
        assert subscription.recipient not in repr(subscription)
        assert repo.eligible(subscription)
        assert not repo.eligible(
            DigestSubscription(user, strategy, "stale@example.test")
        )
        conn.execute(
            "UPDATE operational.accounts SET status='disabled' WHERE id=%s", (account,)
        )
        assert repo.subscriptions(100) == ()
        with pytest.raises(ValidationDomainError):
            repo.subscribe(user, strategy, now)
        conn.execute(
            "UPDATE operational.accounts SET status='active' WHERE id=%s", (account,)
        )
        repo.unsubscribe(user)
        repo.unsubscribe(user)
        assert not repo.eligible(subscription)
        repo.subscribe(user, strategy, now)
        conn.execute(
            "DELETE FROM operational.account_recovery_identity WHERE account_id=%s",
            (account,),
        )
        assert repo.subscriptions(100) == ()
        with pytest.raises(ValidationDomainError):
            repo.subscribe(user, strategy, now)
        conn.rollback()


def test_reservation_budget_freezes_payload_and_prevents_repeat(
    management_database_url,
):
    with psycopg.connect(management_database_url) as conn:
        repo = _setup(conn)
        user, _, strategy = _subscriber(conn, "delivery")
        other, _, other_strategy = _subscriber(conn, "delivery-other")
        now = datetime(2040, 1, 2, tzinfo=UTC)
        week = date(2040, 1, 2)
        for owner, selected in ((user, strategy), (other, other_strategy)):
            repo.subscribe(owner, selected, now)
        delivery = repo.reserve(user, week, now, 1)
        assert delivery is not None
        assert repo.reserve(user, week, now, 100) is None
        assert repo.reserve(other, week, now, 1) is None
        batch, company = uuid4(), uuid4()
        conn.execute(
            "INSERT INTO operational.recommendation_batches(id,user_id,strategy_id,created_at,snapshot) VALUES (%s,%s,%s,%s,'{}')",
            (batch, user, strategy, now),
        )
        assert repo.previous_companies(user) == frozenset()
        recipient = next(
            item.recipient for item in repo.subscriptions(100) if item.user_id == user
        )
        repo.prepare(delivery, batch, recipient, "Subject", "Original body", (company,))
        assert repo.previous_companies(user) == frozenset({company})
        repo.settle(delivery, "unknown", now)
        with pytest.raises(ValidationDomainError):
            repo.prepare(delivery, batch, recipient, "Changed", "Changed", ())
        with pytest.raises(ValidationDomainError):
            repo.settle(delivery, "sent", now)
        row = conn.execute(
            "SELECT state,batch_id,recipient,subject,body,company_ids FROM operational.weekly_digest_deliveries WHERE id=%s",
            (delivery,),
        ).fetchone()
        assert row == (
            "unknown",
            batch,
            recipient,
            "Subject",
            "Original body",
            [str(company)],
        )
        conn.rollback()


def test_concurrent_reservations_share_global_budget_and_weekly_identity(
    management_database_url,
):
    from concurrent.futures import ThreadPoolExecutor

    with psycopg.connect(management_database_url) as conn:
        repo = _setup(conn)
        users = []
        now = datetime(2041, 2, 4, tzinfo=UTC)
        for index in range(3):
            user, _, strategy = _subscriber(conn, f"concurrent-{index}")
            repo.subscribe(user, strategy, now)
            users.append(user)
        conn.commit()

    def reserve(user, limit):
        with psycopg.connect(management_database_url) as conn:
            return PostgresWeeklyDigestRepository(PsycopgDatabaseSession(conn)).reserve(
                user, now.date(), now, limit
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        same = list(pool.map(lambda _: reserve(users[0], 2), range(2)))
        different = list(pool.map(lambda user: reserve(user, 2), users[1:]))
    assert sum(item is not None for item in same) == 1
    assert sum(item is not None for item in different) == 1
    with psycopg.connect(management_database_url) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM operational.weekly_digest_deliveries WHERE created_at=%s",
                (now,),
            ).fetchone()[0]
            == 2
        )


def test_empty_and_failed_deliveries_do_not_suppress_companies_next_month(
    management_database_url,
):
    with psycopg.connect(management_database_url) as conn:
        repo = _setup(conn)
        user, _, strategy = _subscriber(conn, "month-history")
        now = datetime(2042, 3, 3, tzinfo=UTC)
        repo.subscribe(user, strategy, now)
        first = repo.reserve(user, now.date(), now, 100)
        repo.settle(first, "empty", now)
        assert repo.previous_companies(user) == frozenset()
        from datetime import timedelta

        second_day = now + timedelta(days=7)
        second = repo.reserve(user, second_day.date(), second_day, 100)
        repo.settle(second, "failed", second_day)
        assert repo.previous_companies(user) == frozenset()
        batch, company = uuid4(), uuid4()
        conn.execute(
            "INSERT INTO operational.recommendation_batches(id,user_id,strategy_id,created_at,snapshot) VALUES (%s,%s,%s,%s,'{}')",
            (batch, user, strategy, now),
        )
        third_day = now + timedelta(days=35)
        third = repo.reserve(user, third_day.date(), third_day, 100)
        recipient = next(
            item.recipient for item in repo.subscriptions(100) if item.user_id == user
        )
        repo.prepare(third, batch, recipient, "Subject", "Frozen body", (company,))
        repo.settle(third, "sent", third_day)
        assert repo.previous_companies(user) == frozenset({company})
        with pytest.raises(ValidationDomainError):
            repo.settle(third, "unknown", third_day)
        with pytest.raises(ValidationDomainError):
            repo.prepare(third, batch, recipient, "Changed", "Changed", ())
        conn.rollback()

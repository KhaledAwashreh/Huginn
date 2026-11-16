"""Frozen delivery membership in a harness-owned isolated PostgreSQL database."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from tests.management.persistence.prospecting_fixtures import (
    seed_owned_recommendation_revision,
)
from tests.postgres_harness import provisioned_postgres

SCHEMA = Path(__file__).parents[2] / "db/schema/operational-weekly-digest-content.sql"


@pytest.fixture(scope="module")
def content_database_url():
    with provisioned_postgres("huginn_digest_content_test") as url:
        with psycopg.connect(url, autocommit=True) as connection:
            for filename in (
                "operational-recommendations.sql",
                "operational-weekly-digest.sql",
            ):
                connection.execute((SCHEMA.parent / filename).read_text())
            connection.execute(SCHEMA.read_text())
        yield url


def _seed_content(connection):
    identity, recommendation, revision = seed_owned_recommendation_revision(connection)
    now = datetime.now(UTC)
    consent_version = now - timedelta(hours=1)
    connection.execute(
        "INSERT INTO operational.weekly_digest_subscriptions(business_id,enabled,updated_at) VALUES (%s,true,%s)",
        (identity.business_id, consent_version),
    )
    delivery, content, cycle = uuid4(), uuid4(), uuid4()
    connection.execute(
        "INSERT INTO operational.weekly_digest_deliveries(id,business_id,recipient_user_id,week_start,created_at) VALUES (%s,%s,%s,%s,%s)",
        (
            delivery,
            identity.business_id,
            identity.owner_user_id,
            date(2026, 11, 9),
            now,
        ),
    )
    connection.execute(
        "INSERT INTO operational.offer_cycles(id,business_id,company_id,recommendation_id,selected_revision_id,idempotency_key,payload_fingerprint,status,created_at,updated_at,claim_token,lease_expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'token',%s)",
        (
            cycle,
            identity.business_id,
            identity.company_id,
            recommendation.id,
            revision.id,
            str(uuid4()),
            "a" * 64,
            now,
            now,
            now + timedelta(minutes=5),
        ),
    )
    connection.execute(
        "INSERT INTO operational.weekly_digest_contents(id,delivery_id,business_id,recipient_user_id,version,created_at,subscription_updated_at,recipient,subject,body,message_id) VALUES (%s,%s,%s,%s,1,%s,%s,'private@example.test','Weekly','Frozen explanation','<content@example.test>')",
        (
            content,
            delivery,
            identity.business_id,
            identity.owner_user_id,
            now,
            consent_version,
        ),
    )
    connection.execute(
        "INSERT INTO operational.weekly_digest_members(content_id,delivery_id,business_id,company_id,recommendation_id,assessment_revision_id,offer_cycle_id,position) VALUES (%s,%s,%s,%s,%s,%s,%s,1)",
        (
            content,
            delivery,
            identity.business_id,
            identity.company_id,
            recommendation.id,
            revision.id,
            cycle,
        ),
    )
    connection.execute(
        "UPDATE operational.weekly_digest_deliveries SET current_content_id=%s,version=version+1 WHERE id=%s",
        (content, delivery),
    )
    return identity, delivery, content, cycle


def test_frozen_content_and_members_cannot_be_rewritten_or_extended(
    content_database_url,
):
    with psycopg.connect(content_database_url) as connection:
        identity, delivery, content, cycle = _seed_content(connection)
    with psycopg.connect(content_database_url, autocommit=True) as connection:
        for sql, arguments in (
            (
                "UPDATE operational.weekly_digest_contents SET body='overwritten' WHERE id=%s",
                (content,),
            ),
            ("DELETE FROM operational.weekly_digest_contents WHERE id=%s", (content,)),
            (
                "UPDATE operational.weekly_digest_members SET position=2 WHERE content_id=%s",
                (content,),
            ),
            (
                "DELETE FROM operational.weekly_digest_members WHERE content_id=%s",
                (content,),
            ),
            (
                "INSERT INTO operational.weekly_digest_members SELECT content_id,delivery_id,business_id,company_id,recommendation_id,assessment_revision_id,offer_cycle_id,2 FROM operational.weekly_digest_members WHERE content_id=%s",
                (content,),
            ),
        ):
            with pytest.raises(psycopg.Error) as failure:
                connection.execute(sql, arguments)
            assert failure.value.sqlstate == "55000"
        assert (
            connection.execute(
                "SELECT body FROM operational.weekly_digest_contents WHERE id=%s",
                (content,),
            ).fetchone()[0]
            == "Frozen explanation"
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_members WHERE content_id=%s",
                (content,),
            ).fetchone()[0]
            == 1
        )
        connection.execute(SCHEMA.read_text())
        assert (
            connection.execute(
                "SELECT body FROM operational.weekly_digest_contents WHERE id=%s",
                (content,),
            ).fetchone()[0]
            == "Frozen explanation"
        )


def _copy_content(connection, original, replacement, *, subscription_updated_at=None):
    connection.execute(
        "INSERT INTO operational.weekly_digest_contents(id,delivery_id,business_id,recipient_user_id,version,created_at,subscription_updated_at,recipient,subject,body,message_id) SELECT %s,delivery_id,business_id,recipient_user_id,version+1,created_at,COALESCE(%s,subscription_updated_at),recipient,subject,'Replacement explanation','<replacement@example.test>' FROM operational.weekly_digest_contents WHERE id=%s",
        (replacement, subscription_updated_at, original),
    )


def test_replacement_retains_each_frozen_consent_version(content_database_url):
    with psycopg.connect(content_database_url) as connection:
        identity, delivery, original, _ = _seed_content(connection)
        accepted_version = connection.execute(
            "SELECT subscription_updated_at FROM operational.weekly_digest_contents WHERE id=%s",
            (original,),
        ).fetchone()[0]
        replacement = uuid4()
        new_version = accepted_version + timedelta(hours=1)
        connection.execute(
            "UPDATE operational.weekly_digest_subscriptions SET updated_at=%s WHERE business_id=%s",
            (new_version, identity.business_id),
        )
        _copy_content(
            connection, original, replacement, subscription_updated_at=new_version
        )
        connection.execute(
            "INSERT INTO operational.weekly_digest_members SELECT %s,delivery_id,business_id,company_id,recommendation_id,assessment_revision_id,offer_cycle_id,position FROM operational.weekly_digest_members WHERE content_id=%s",
            (replacement, original),
        )
    with psycopg.connect(content_database_url) as connection:
        assert connection.execute(
            "SELECT version,subscription_updated_at FROM operational.weekly_digest_contents WHERE delivery_id=%s ORDER BY version",
            (delivery,),
        ).fetchall() == [(1, accepted_version), (2, new_version)]


def test_content_requires_exact_owned_revision_and_cycle_membership(
    content_database_url,
):
    with psycopg.connect(content_database_url) as connection:
        identity, delivery, original, _ = _seed_content(connection)
        _, _, foreign_content, foreign_cycle = _seed_content(connection)
    with (
        pytest.raises(psycopg.errors.ForeignKeyViolation),
        psycopg.connect(content_database_url) as connection,
    ):
        replacement = uuid4()
        _copy_content(connection, original, replacement)
        connection.execute(
            "INSERT INTO operational.weekly_digest_members SELECT %s,delivery_id,business_id,company_id,recommendation_id,assessment_revision_id,%s,position FROM operational.weekly_digest_members WHERE content_id=%s",
            (replacement, foreign_cycle, original),
        )
    with (
        pytest.raises(psycopg.errors.ForeignKeyViolation),
        psycopg.connect(content_database_url) as connection,
    ):
        connection.execute(
            "UPDATE operational.weekly_digest_deliveries SET current_content_id=%s,version=version+1 WHERE id=%s",
            (foreign_content, delivery),
        )
    with psycopg.connect(content_database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_contents WHERE business_id=%s",
                (identity.business_id,),
            ).fetchone()[0]
            == 1
        )


def test_empty_content_cannot_commit_and_replacement_preserves_original(
    content_database_url,
):
    with psycopg.connect(content_database_url) as connection:
        identity, delivery, original, _ = _seed_content(connection)
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        psycopg.connect(content_database_url) as connection,
    ):
        _copy_content(connection, original, uuid4())
    replacement = uuid4()
    with psycopg.connect(content_database_url) as connection:
        _copy_content(connection, original, replacement)
        connection.execute(
            "INSERT INTO operational.weekly_digest_members SELECT %s,delivery_id,business_id,company_id,recommendation_id,assessment_revision_id,offer_cycle_id,position FROM operational.weekly_digest_members WHERE content_id=%s",
            (replacement, original),
        )
        connection.execute(
            "UPDATE operational.weekly_digest_deliveries SET current_content_id=%s,version=version+1 WHERE id=%s",
            (replacement, delivery),
        )
    with psycopg.connect(content_database_url) as connection:
        assert connection.execute(
            "SELECT version,body FROM operational.weekly_digest_contents WHERE delivery_id=%s ORDER BY version",
            (delivery,),
        ).fetchall() == [(1, "Frozen explanation"), (2, "Replacement explanation")]


def test_early_constraint_flush_cannot_commit_later_nonconsecutive_members(
    content_database_url,
):
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        psycopg.connect(content_database_url) as connection,
    ):
        identity, delivery, content, cycle = _seed_content(connection)
        connection.execute(
            "SET CONSTRAINTS operational.weekly_digest_contents_complete IMMEDIATE"
        )
        company = connection.execute(
            "INSERT INTO gold.company(domain,name) VALUES (%s,'Another company') RETURNING id",
            (f"{uuid4()}.example.test",),
        ).fetchone()[0]
        second_identity = replace(identity, company_id=company)
        _, recommendation, revision = seed_owned_recommendation_revision(
            connection, second_identity
        )
        second_cycle = uuid4()
        connection.execute(
            "INSERT INTO operational.offer_cycles(id,business_id,company_id,recommendation_id,selected_revision_id,idempotency_key,payload_fingerprint,status,created_at,updated_at,claim_token,lease_expires_at) SELECT %s,business_id,%s,%s,%s,%s,payload_fingerprint,status,created_at,updated_at,claim_token,lease_expires_at FROM operational.offer_cycles WHERE id=%s",
            (
                second_cycle,
                company,
                recommendation.id,
                revision.id,
                str(uuid4()),
                cycle,
            ),
        )
        connection.execute(
            "INSERT INTO operational.weekly_digest_members(content_id,delivery_id,business_id,company_id,recommendation_id,assessment_revision_id,offer_cycle_id,position) VALUES (%s,%s,%s,%s,%s,%s,%s,3)",
            (
                content,
                delivery,
                identity.business_id,
                company,
                recommendation.id,
                revision.id,
                second_cycle,
            ),
        )


def test_weekly_reservation_identity_is_immutable(content_database_url):
    with psycopg.connect(content_database_url) as connection:
        _, delivery, _, _ = _seed_content(connection)
    with psycopg.connect(content_database_url, autocommit=True) as connection:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                "UPDATE operational.weekly_digest_deliveries SET week_start=%s WHERE id=%s",
                (date(2026, 11, 16), delivery),
            )
        assert connection.execute(
            "SELECT week_start FROM operational.weekly_digest_deliveries WHERE id=%s",
            (delivery,),
        ).fetchone()[0] == date(2026, 11, 9)


def test_unknown_weekly_recovery_requires_matching_attributed_history(
    content_database_url,
):
    with psycopg.connect(content_database_url) as connection:
        identity, delivery, content, _ = _seed_content(connection)
        created = connection.execute(
            "SELECT created_at FROM operational.weekly_digest_deliveries WHERE id=%s",
            (delivery,),
        ).fetchone()[0]
        authorized = created + timedelta(seconds=1)
        accepted = created + timedelta(seconds=2)
        unknown = created + timedelta(seconds=5)
        recovered = created + timedelta(days=35)
        connection.execute(
            "UPDATE operational.weekly_digest_deliveries SET state='sending',version=version+1,sending_started_at=%s WHERE id=%s",
            (authorized, delivery),
        )
        connection.execute(
            "UPDATE operational.weekly_digest_deliveries SET state='unknown',version=version+1,settled_at=%s WHERE id=%s",
            (unknown, delivery),
        )
        connection.execute(
            "INSERT INTO operational.weekly_digest_delivery_events(id,delivery_id,business_id,delivery_version,event_kind,recorded_at,content_id) VALUES (%s,%s,%s,4,'unknown',%s,%s)",
            (uuid4(), delivery, identity.business_id, unknown, content),
        )
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        psycopg.connect(content_database_url) as connection,
    ):
        connection.execute(
            "UPDATE operational.weekly_digest_deliveries SET state='sent',version=version+1,settled_at=%s,accepted_at=%s WHERE id=%s",
            (recovered, accepted, delivery),
        )
    event_id = uuid4()
    with psycopg.connect(content_database_url) as connection:
        connection.execute(
            "INSERT INTO operational.weekly_digest_delivery_events(id,delivery_id,business_id,delivery_version,event_kind,recorded_at,content_id,actor_user_id,reason,outcome,accepted_at) VALUES (%s,%s,%s,5,'unknown_resolved',%s,%s,%s,'Confirmed actual handoff','sent',%s)",
            (
                event_id,
                delivery,
                identity.business_id,
                recovered,
                content,
                identity.owner_user_id,
                accepted,
            ),
        )
        connection.execute(
            "UPDATE operational.weekly_digest_deliveries SET state='sent',version=version+1,settled_at=%s,accepted_at=%s WHERE id=%s",
            (recovered, accepted, delivery),
        )
    with psycopg.connect(content_database_url, autocommit=True) as connection:
        assert connection.execute(
            "SELECT event_kind,recorded_at,accepted_at FROM operational.weekly_digest_delivery_events WHERE delivery_id=%s ORDER BY delivery_version",
            (delivery,),
        ).fetchall() == [
            ("unknown", unknown, None),
            ("unknown_resolved", recovered, accepted),
        ]
        assert connection.execute(
            "SELECT state,accepted_at,settled_at FROM operational.weekly_digest_deliveries WHERE id=%s",
            (delivery,),
        ).fetchone() == ("sent", accepted, recovered)
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute(
                "UPDATE operational.weekly_digest_delivery_events SET reason='rewritten' WHERE id=%s",
                (event_id,),
            )

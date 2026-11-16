from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

TABLES = (
    "recommendations",
    "assessment_revisions",
    "offer_cycles",
    "offer_cycle_events",
    "prospects",
    "prospect_origins",
    "prospect_activities",
    "suppression_blocks",
    "command_receipts",
    "recommendation_assessment_feedback",
)


def _seed_owner_company(connection):
    account_id = connection.execute(
        "INSERT INTO operational.accounts(username,password_hash) "
        "VALUES (%s,'test-hash') RETURNING id",
        (f"prospecting-{uuid4()}@example.test",),
    ).fetchone()[0]
    user_id = connection.execute(
        "INSERT INTO operational.users "
        "(account_id,first_name,last_name,email,phone_number,country_of_residence) "
        "VALUES (%s,'Ada','Lovelace',%s,'+12025550123','US') RETURNING id",
        (account_id, f"{uuid4()}@example.test"),
    ).fetchone()[0]
    business_id = connection.execute(
        "INSERT INTO operational.businesses(owner_user_id) VALUES (%s) RETURNING id",
        (user_id,),
    ).fetchone()[0]
    company_id = connection.execute(
        "INSERT INTO gold.company(domain,name) VALUES (%s,'Schema Fixture') RETURNING id",
        (f"{uuid4()}.example.test",),
    ).fetchone()[0]
    return user_id, business_id, company_id


def _insert_recommendation(connection, business_id, company_id, *, status="open"):
    now = datetime.now(UTC)
    recommendation_id = uuid4()
    connection.execute(
        "INSERT INTO operational.recommendations "
        "(id,business_id,company_id,status,created_at,updated_at,resolved_at,resolved_by_user_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            recommendation_id,
            business_id,
            company_id,
            status,
            now,
            now,
            None if status == "open" else now,
            None
            if status == "open"
            else connection.execute(
                "SELECT owner_user_id FROM operational.businesses WHERE id=%s",
                (business_id,),
            ).fetchone()[0],
        ),
    )
    return recommendation_id


def _insert_revision(
    connection, business_id, company_id, recommendation_id, *, strategy_assessments=None
):
    revision_id = uuid4()
    strategy_assessments = strategy_assessments or [
        {"strategy_id": str(uuid4()), "score": 45}
    ]
    connection.execute(
        "INSERT INTO operational.assessment_revisions "
        "(id,recommendation_id,business_id,company_id,revision_number,assessed_at,"
        "strategy_assessments,professional_profile_snapshot,evidence_snapshots,"
        "evidence_observation_ids,policy_versions) "
        "VALUES (%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s)",
        (
            revision_id,
            recommendation_id,
            business_id,
            company_id,
            datetime.now(UTC),
            Jsonb(strategy_assessments),
            Jsonb({"headline": "Independent consultant"}),
            Jsonb([{"observation_id": str(uuid4()), "quote": "Hiring"}]),
            [uuid4()],
            ["company-fit-v1", "lexical-v1"],
        ),
    )
    connection.execute(
        "UPDATE operational.recommendations SET current_revision_id=%s,"
        "version=version+1,updated_at=%s WHERE id=%s",
        (revision_id, datetime.now(UTC), recommendation_id),
    )
    return revision_id


def test_fresh_schema_bootstraps_all_business_owned_prospecting_tables(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        present = {
            name: connection.execute(
                "SELECT to_regclass(%s)", (f"operational.{name}",)
            ).fetchone()[0]
            for name in TABLES
        }
    assert all(present.values()), present


def test_recommendation_revision_offer_and_feedback_keep_exact_membership(
    management_database_url,
):
    now = datetime.now(UTC)
    with psycopg.connect(management_database_url) as connection:
        actor_id, business_id, company_id = _seed_owner_company(connection)
        offering_id = connection.execute(
            "INSERT INTO operational.service_offerings(business_id,name,description) "
            "VALUES (%s,'Research','Research source data') RETURNING id",
            (business_id,),
        ).fetchone()[0]
        profile_id = connection.execute(
            "INSERT INTO operational.ideal_client_profiles(business_id,name) "
            "VALUES (%s,'SaaS') RETURNING id",
            (business_id,),
        ).fetchone()[0]
        strategy_id = connection.execute(
            "INSERT INTO operational.client_discovery_strategies "
            "(business_id,name,service_offering_id,ideal_client_profile_id) "
            "VALUES (%s,'Research for SaaS',%s,%s) RETURNING id",
            (business_id, offering_id, profile_id),
        ).fetchone()[0]
        other_company_id = connection.execute(
            "INSERT INTO gold.company(domain,name) VALUES (%s,'Other') RETURNING id",
            (f"{uuid4()}.example.test",),
        ).fetchone()[0]
        recommendation_id = _insert_recommendation(connection, business_id, company_id)
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "UPDATE operational.recommendations SET resolution_reason='not open',"
                "version=version+1,updated_at=updated_at+interval '1 second' WHERE id=%s",
                (recommendation_id,),
            )
        revision_id = _insert_revision(
            connection,
            business_id,
            company_id,
            recommendation_id,
            strategy_assessments=[
                {
                    "strategy_id": str(strategy_id),
                    "offering_id": str(offering_id),
                    "ideal_client_profile_id": str(profile_id),
                    "score": 45,
                }
            ],
        )
        other_recommendation_id = _insert_recommendation(
            connection, business_id, other_company_id
        )
        other_revision_id = _insert_revision(
            connection, business_id, other_company_id, other_recommendation_id
        )
        with (
            pytest.raises(psycopg.errors.ForeignKeyViolation),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.recommendations SET current_revision_id=%s,"
                "version=version+1,updated_at=updated_at+interval '1 second' WHERE id=%s",
                (other_revision_id, recommendation_id),
            )

        with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
            _insert_recommendation(connection, business_id, company_id)

        with (
            pytest.raises(psycopg.errors.ForeignKeyViolation),
            connection.transaction(),
        ):
            connection.execute(
                "INSERT INTO operational.offer_cycles "
                "(id,business_id,company_id,recommendation_id,selected_revision_id,"
                "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
                "claim_token,lease_expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'token',%s)",
                (
                    uuid4(),
                    business_id,
                    company_id,
                    recommendation_id,
                    other_revision_id,
                    "wrong-revision",
                    "a" * 64,
                    now,
                    now,
                    now + timedelta(minutes=5),
                ),
            )
        connection.execute(
            "DELETE FROM operational.client_discovery_strategies WHERE id=%s",
            (strategy_id,),
        )
        connection.execute(
            "DELETE FROM operational.service_offerings WHERE id=%s", (offering_id,)
        )
        connection.execute(
            "DELETE FROM operational.ideal_client_profiles WHERE id=%s", (profile_id,)
        )

        offer_cycle_id = uuid4()
        connection.execute(
            "INSERT INTO operational.offer_cycles "
            "(id,business_id,company_id,recommendation_id,selected_revision_id,"
            "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
            "claim_token,lease_expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'token',%s)",
            (
                offer_cycle_id,
                business_id,
                company_id,
                recommendation_id,
                revision_id,
                "request",
                "b" * 64,
                now,
                now,
                now + timedelta(minutes=5),
            ),
        )
        with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.offer_cycles "
                "(id,business_id,company_id,recommendation_id,selected_revision_id,"
                "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
                "claim_token,lease_expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'token-2',%s)",
                (
                    uuid4(),
                    business_id,
                    company_id,
                    recommendation_id,
                    revision_id,
                    "another-request",
                    "d" * 64,
                    now,
                    now,
                    now + timedelta(minutes=5),
                ),
            )
        connection.execute(
            "INSERT INTO operational.recommendation_assessment_feedback "
            "(id,business_id,recommendation_id,assessment_revision_id,actor_user_id,recorded_at,payload) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                uuid4(),
                business_id,
                recommendation_id,
                revision_id,
                actor_id,
                now,
                Jsonb(
                    {"usefulness": "useful", "next_step": "none", "outcome": "unknown"}
                ),
            ),
        )
        persisted = connection.execute(
            "SELECT strategy_assessments->0->>'score',"
            "professional_profile_snapshot->>'headline',"
            "evidence_snapshots->0->>'quote',policy_versions "
            "FROM operational.assessment_revisions WHERE id=%s",
            (revision_id,),
        ).fetchone()
        assert persisted == (
            "45",
            "Independent consultant",
            "Hiring",
            ["company-fit-v1", "lexical-v1"],
        )
        assert connection.execute(
            "SELECT strategy_assessments->0->>'strategy_id',"
            "strategy_assessments->0->>'offering_id',"
            "strategy_assessments->0->>'ideal_client_profile_id' "
            "FROM operational.assessment_revisions WHERE id=%s",
            (revision_id,),
        ).fetchone() == (str(strategy_id), str(offering_id), str(profile_id))
        created_at = now - timedelta(minutes=4)
        handoff_at = now - timedelta(minutes=2)
        uncertain_at = now - timedelta(minutes=1)
        resolved_at = now
        cycle_id = connection.execute(
            "INSERT INTO operational.offer_cycles "
            "(id,business_id,company_id,recommendation_id,selected_revision_id,"
            "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
            "claim_token,lease_expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'send-token',%s) "
            "RETURNING id",
            (
                uuid4(),
                business_id,
                other_company_id,
                other_recommendation_id,
                other_revision_id,
                "recovered-send",
                "e" * 64,
                created_at,
                created_at,
                created_at + timedelta(minutes=5),
            ),
        ).fetchone()[0]
        connection.execute(
            "UPDATE operational.offer_cycles SET status='sending',updated_at=%s,"
            "lease_expires_at=NULL,sending_started_at=%s WHERE id=%s",
            (handoff_at, handoff_at, cycle_id),
        )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='unknown',updated_at=%s,settled_at=%s "
            "WHERE id=%s",
            (uncertain_at, uncertain_at, cycle_id),
        )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='confirmed',updated_at=%s,presented_at=%s,settled_at=%s "
            "WHERE id=%s",
            (resolved_at, handoff_at, resolved_at, cycle_id),
        )
        event_id = uuid4()
        connection.execute(
            "INSERT INTO operational.offer_cycle_events "
            "(id,offer_cycle_id,business_id,company_id,event_kind,actor_user_id,reason,"
            "outcome,presented_at,resolved_at,recorded_at,payload) "
            "VALUES (%s,%s,%s,%s,'unknown_resolved',%s,'confirmed from delivery receipt',"
            "'confirmed',%s,%s,%s,%s)",
            (
                event_id,
                cycle_id,
                business_id,
                other_company_id,
                actor_id,
                handoff_at,
                resolved_at,
                resolved_at,
                Jsonb({"source": "provider receipt"}),
            ),
        )
        assert connection.execute(
            "SELECT actor_user_id,reason,outcome,presented_at,resolved_at "
            "FROM operational.offer_cycle_events WHERE id=%s",
            (event_id,),
        ).fetchone() == (
            actor_id,
            "confirmed from delivery receipt",
            "confirmed",
            handoff_at,
            resolved_at,
        )
        with (
            pytest.raises(psycopg.errors.ForeignKeyViolation),
            connection.transaction(),
        ):
            connection.execute(
                "INSERT INTO operational.offer_cycle_events "
                "(id,offer_cycle_id,business_id,company_id,event_kind,actor_user_id,reason,recorded_at) "
                "VALUES (%s,%s,%s,%s,'sending_authorized',%s,'reason',%s)",
                (
                    uuid4(),
                    cycle_id,
                    business_id,
                    other_company_id,
                    uuid4(),
                    resolved_at,
                ),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.offer_cycle_events SET reason='rewritten' WHERE id=%s",
                (event_id,),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "DELETE FROM operational.offer_cycles WHERE id=%s", (cycle_id,)
            )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.offer_cycle_events "
                "(id,offer_cycle_id,business_id,company_id,event_kind,actor_user_id,reason,"
                "outcome,presented_at,resolved_at,recorded_at) "
                "VALUES (%s,%s,%s,%s,'unknown_resolved',%s,'missing outcome',NULL,%s,%s,%s)",
                (
                    uuid4(),
                    cycle_id,
                    business_id,
                    other_company_id,
                    actor_id,
                    handoff_at,
                    resolved_at,
                    resolved_at,
                ),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "DELETE FROM operational.recommendations WHERE id=%s",
                (recommendation_id,),
            )
        with (
            pytest.raises(psycopg.errors.ForeignKeyViolation),
            connection.transaction(),
        ):
            connection.execute(
                "INSERT INTO operational.recommendation_assessment_feedback "
                "(id,business_id,recommendation_id,assessment_revision_id,actor_user_id,recorded_at,payload) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid4(),
                    business_id,
                    recommendation_id,
                    revision_id,
                    uuid4(),
                    now,
                    Jsonb({"usefulness": "useful"}),
                ),
            )


def test_prospect_origins_and_activities_are_exact_and_append_only(
    management_database_url,
):
    now = datetime.now(UTC)
    with psycopg.connect(management_database_url) as connection:
        actor_id, business_id, company_id = _seed_owner_company(connection)
        recommendation_id = _insert_recommendation(connection, business_id, company_id)
        revision_id = _insert_revision(
            connection, business_id, company_id, recommendation_id
        )
        other_company_id = connection.execute(
            "INSERT INTO gold.company(domain,name) VALUES (%s,'Different origin') RETURNING id",
            (f"{uuid4()}.example.test",),
        ).fetchone()[0]
        other_recommendation_id = _insert_recommendation(
            connection, business_id, other_company_id
        )
        other_revision_id = _insert_revision(
            connection, business_id, other_company_id, other_recommendation_id
        )
        prospect_id = uuid4()
        connection.execute(
            "INSERT INTO operational.prospects "
            "(id,business_id,company_id,stage,created_at,updated_at) "
            "VALUES (%s,%s,%s,'saved',%s,%s)",
            (prospect_id, business_id, company_id, now, now),
        )
        origin_id = uuid4()
        connection.execute(
            "INSERT INTO operational.prospect_origins "
            "(id,business_id,company_id,prospect_id,recommendation_id,"
            "assessment_revision_id,created_by_user_id,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                origin_id,
                business_id,
                company_id,
                prospect_id,
                recommendation_id,
                revision_id,
                actor_id,
                now,
            ),
        )
        with (
            pytest.raises(psycopg.errors.ForeignKeyViolation),
            connection.transaction(),
        ):
            connection.execute(
                "INSERT INTO operational.prospect_origins "
                "(id,business_id,company_id,prospect_id,recommendation_id,"
                "assessment_revision_id,created_by_user_id,created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid4(),
                    business_id,
                    company_id,
                    prospect_id,
                    recommendation_id,
                    other_revision_id,
                    actor_id,
                    now,
                ),
            )
        activity_id = uuid4()
        connection.execute(
            "INSERT INTO operational.prospect_activities "
            "(id,business_id,prospect_id,actor_user_id,idempotency_key,payload_fingerprint,"
            "kind,occurred_at,recorded_at,payload,origin_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,'prospect_saved',%s,%s,%s,%s)",
            (
                activity_id,
                business_id,
                prospect_id,
                actor_id,
                "save-key",
                "f" * 64,
                now,
                now,
                Jsonb({"origin_id": str(origin_id)}),
                origin_id,
            ),
        )
        with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.prospect_origins "
                "(id,business_id,company_id,prospect_id,recommendation_id,"
                "assessment_revision_id,created_by_user_id,created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid4(),
                    business_id,
                    company_id,
                    prospect_id,
                    recommendation_id,
                    revision_id,
                    actor_id,
                    now,
                ),
            )
        with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.prospect_activities "
                "(id,business_id,prospect_id,actor_user_id,idempotency_key,"
                "payload_fingerprint,kind,occurred_at,recorded_at,payload,origin_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,'prospect_saved',%s,%s,%s,%s)",
                (
                    uuid4(),
                    business_id,
                    prospect_id,
                    actor_id,
                    "different-save-key",
                    "1" * 64,
                    now,
                    now,
                    Jsonb({"origin_id": str(origin_id)}),
                    origin_id,
                ),
            )
        with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.prospect_activities "
                "(id,business_id,prospect_id,actor_user_id,idempotency_key,"
                "payload_fingerprint,kind,occurred_at,recorded_at,payload) "
                "VALUES (%s,%s,%s,%s,%s,%s,'note_added',%s,%s,%s)",
                (
                    uuid4(),
                    business_id,
                    prospect_id,
                    actor_id,
                    "save-key",
                    "2" * 64,
                    now,
                    now,
                    Jsonb({"note": "retry"}),
                ),
            )

        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.assessment_revisions SET professional_profile_snapshot='{}' "
                "WHERE id=%s",
                (revision_id,),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "DELETE FROM operational.prospect_origins WHERE id=%s", (origin_id,)
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.prospect_activities SET payload='{}' WHERE id=%s",
                (activity_id,),
            )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.prospect_activities "
                "(id,business_id,prospect_id,actor_user_id,idempotency_key,"
                "payload_fingerprint,kind,occurred_at,recorded_at,payload,correction_of_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,'correction',%s,%s,%s,%s)",
                (
                    uuid4(),
                    business_id,
                    prospect_id,
                    actor_id,
                    "correction-key",
                    "0" * 64,
                    now - timedelta(seconds=1),
                    now - timedelta(seconds=1),
                    Jsonb({"prior": "a", "replacement": "b"}),
                    activity_id,
                ),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "DELETE FROM operational.prospects WHERE id=%s", (prospect_id,)
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.prospects SET company_id=%s,version=version+1,"
                "updated_at=updated_at+interval '1 second' WHERE id=%s",
                (uuid4(), prospect_id),
            )


def test_unknown_offer_cannot_be_resolved_without_attributed_event(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        _, business_id, company_id = _seed_owner_company(connection)
        recommendation_id = _insert_recommendation(connection, business_id, company_id)
        revision_id = _insert_revision(
            connection, business_id, company_id, recommendation_id
        )
        connection.commit()

    now = datetime.now(UTC)
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        psycopg.connect(management_database_url) as connection,
    ):
        cycle_id = uuid4()
        connection.execute(
            "INSERT INTO operational.offer_cycles "
            "(id,business_id,company_id,recommendation_id,selected_revision_id,"
            "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
            "claim_token,lease_expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'token',%s)",
            (
                cycle_id,
                business_id,
                company_id,
                recommendation_id,
                revision_id,
                "unknown-no-audit",
                "7" * 64,
                now,
                now,
                now + timedelta(minutes=5),
            ),
        )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='sending',updated_at=%s,"
            "lease_expires_at=NULL,sending_started_at=%s WHERE id=%s",
            (now, now, cycle_id),
        )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='unknown',updated_at=%s,settled_at=%s "
            "WHERE id=%s",
            (now, now, cycle_id),
        )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='abandoned',updated_at=%s WHERE id=%s",
            (now + timedelta(seconds=1), cycle_id),
        )


def test_suppression_is_independent_and_offer_uncertainty_has_no_expiry(
    management_database_url,
):
    now = datetime.now(UTC)
    with psycopg.connect(management_database_url) as connection:
        actor_id, business_id, company_id = _seed_owner_company(connection)
        for kind, expiry in (
            ("cooldown", now + timedelta(days=30)),
            ("pause", now + timedelta(days=7)),
            ("rejection", None),
        ):
            connection.execute(
                "INSERT INTO operational.suppression_blocks "
                "(id,business_id,company_id,kind,created_at,effective_at,created_by_user_id,expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid4(),
                    business_id,
                    company_id,
                    kind,
                    now,
                    now,
                    None if kind == "cooldown" else actor_id,
                    expiry,
                ),
            )
        pause_id = connection.execute(
            "SELECT id FROM operational.suppression_blocks "
            "WHERE business_id=%s AND kind='pause'",
            (business_id,),
        ).fetchone()[0]
        connection.execute(
            "UPDATE operational.suppression_blocks SET cleared_at=%s,cleared_by_user_id=%s,version=version+1 WHERE id=%s",
            (now, actor_id, pause_id),
        )
        assert connection.execute(
            "SELECT kind,cleared_at FROM operational.suppression_blocks WHERE business_id=%s ORDER BY kind",
            (business_id,),
        ).fetchall() == [("cooldown", None), ("pause", now), ("rejection", None)]
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "DELETE FROM operational.suppression_blocks "
                "WHERE business_id=%s AND kind='rejection'",
                (business_id,),
            )

        recommendation_id = _insert_recommendation(connection, business_id, company_id)
        revision_id = _insert_revision(
            connection, business_id, company_id, recommendation_id
        )
        stale_created_at = now - timedelta(days=31)
        stale_cycle_id = uuid4()
        connection.execute(
            "INSERT INTO operational.offer_cycles "
            "(id,business_id,company_id,recommendation_id,selected_revision_id,"
            "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
            "claim_token,lease_expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'old-token',%s)",
            (
                stale_cycle_id,
                business_id,
                company_id,
                recommendation_id,
                revision_id,
                "expired-preparing",
                "c" * 64,
                stale_created_at,
                stale_created_at,
                stale_created_at + timedelta(minutes=5),
            ),
        )
        with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.offer_cycles "
                "(id,business_id,company_id,recommendation_id,selected_revision_id,"
                "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
                "claim_token,lease_expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'new-token',%s)",
                (
                    uuid4(),
                    business_id,
                    company_id,
                    recommendation_id,
                    revision_id,
                    "new-preparing",
                    "d" * 64,
                    now,
                    now,
                    now + timedelta(minutes=5),
                ),
            )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='sending',updated_at=%s,"
            "lease_expires_at=NULL,sending_started_at=%s WHERE id=%s",
            (now, now, stale_cycle_id),
        )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "UPDATE operational.offer_cycles SET status='unknown',updated_at=%s,"
                "settled_at=%s,lease_expires_at=%s WHERE id=%s",
                (
                    now + timedelta(seconds=1),
                    now + timedelta(seconds=1),
                    now + timedelta(minutes=5),
                    stale_cycle_id,
                ),
            )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='unknown',updated_at=%s,settled_at=%s "
            "WHERE id=%s",
            (now + timedelta(seconds=1), now + timedelta(seconds=1), stale_cycle_id),
        )
        assert connection.execute(
            "SELECT status,lease_expires_at FROM operational.offer_cycles WHERE id=%s",
            (stale_cycle_id,),
        ).fetchone() == ("unknown", None)
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.offer_cycles "
                "(id,business_id,company_id,recommendation_id,selected_revision_id,"
                "idempotency_key,payload_fingerprint,status,created_at,updated_at,claim_token) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'token')",
                (
                    uuid4(),
                    business_id,
                    company_id,
                    recommendation_id,
                    revision_id,
                    "missing-lease",
                    "8" * 64,
                    now,
                    now,
                ),
            )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.offer_cycles "
                "(id,business_id,company_id,recommendation_id,selected_revision_id,"
                "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
                "claim_token,lease_expires_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'token','infinity')",
                (
                    uuid4(),
                    business_id,
                    company_id,
                    recommendation_id,
                    revision_id,
                    "infinite-lease",
                    "6" * 64,
                    now,
                    now,
                ),
            )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.offer_cycles "
                "(id,business_id,company_id,recommendation_id,selected_revision_id,"
                "idempotency_key,payload_fingerprint,status,created_at,updated_at,claim_token) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'token')",
                (
                    uuid4(),
                    business_id,
                    company_id,
                    recommendation_id,
                    revision_id,
                    "missing-lease",
                    "8" * 64,
                    now,
                    now,
                ),
            )


def test_open_recommendation_and_prospect_pair_are_unique_under_concurrent_writes(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        _, business_id, company_id = _seed_owner_company(connection)
        connection.commit()
    barrier = Barrier(2)

    def insert_open_recommendation():
        with psycopg.connect(management_database_url) as connection:
            recommendation_id = uuid4()
            now = datetime.now(UTC)
            barrier.wait()
            try:
                connection.execute(
                    "INSERT INTO operational.recommendations "
                    "(id,business_id,company_id,status,created_at,updated_at) "
                    "VALUES (%s,%s,%s,'open',%s,%s)",
                    (recommendation_id, business_id, company_id, now, now),
                )
                connection.commit()
                return True
            except psycopg.errors.UniqueViolation:
                connection.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        recommendation_results = tuple(
            pool.map(lambda _: insert_open_recommendation(), range(2))
        )
    assert recommendation_results.count(True) == 1

    barrier = Barrier(2)

    def insert_prospect():
        with psycopg.connect(management_database_url) as connection:
            prospect_id = uuid4()
            now = datetime.now(UTC)
            barrier.wait()
            try:
                connection.execute(
                    "INSERT INTO operational.prospects "
                    "(id,business_id,company_id,stage,created_at,updated_at) "
                    "VALUES (%s,%s,%s,'saved',%s,%s)",
                    (prospect_id, business_id, company_id, now, now),
                )
                connection.commit()
                return True
            except psycopg.errors.UniqueViolation:
                connection.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        prospect_results = tuple(pool.map(lambda _: insert_prospect(), range(2)))
    assert prospect_results.count(True) == 1

    with psycopg.connect(management_database_url) as connection:
        offer_company_id = connection.execute(
            "INSERT INTO gold.company(domain,name) VALUES (%s,'Offer race') RETURNING id",
            (f"{uuid4()}.example.test",),
        ).fetchone()[0]
        recommendation_id = _insert_recommendation(
            connection, business_id, offer_company_id
        )
        revision_id = _insert_revision(
            connection, business_id, offer_company_id, recommendation_id
        )
        connection.commit()
    barrier = Barrier(2)

    def acquire_offer_cycle():
        with psycopg.connect(management_database_url) as connection:
            now = datetime.now(UTC)
            barrier.wait()
            try:
                connection.execute(
                    "INSERT INTO operational.offer_cycles "
                    "(id,business_id,company_id,recommendation_id,selected_revision_id,"
                    "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
                    "claim_token,lease_expires_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,%s,%s)",
                    (
                        uuid4(),
                        business_id,
                        offer_company_id,
                        recommendation_id,
                        revision_id,
                        f"claim-{uuid4()}",
                        "a" * 64,
                        now,
                        now,
                        str(uuid4()),
                        now + timedelta(minutes=5),
                    ),
                )
                connection.commit()
                return True
            except psycopg.errors.UniqueViolation:
                connection.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        offer_results = tuple(pool.map(lambda _: acquire_offer_cycle(), range(2)))
    assert offer_results.count(True) == 1


def test_resolved_recommendation_records_late_confirmed_handoff_without_reopening(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        actor_id, business_id, company_id = _seed_owner_company(connection)
        recommendation_id = _insert_recommendation(connection, business_id, company_id)
        revision_id = _insert_revision(
            connection, business_id, company_id, recommendation_id
        )
        authorization_at = datetime.now(UTC)
        resolution_at = authorization_at + timedelta(seconds=1)
        handoff_at = resolution_at + timedelta(seconds=1)
        recorded_at = handoff_at + timedelta(seconds=1)
        cycle_id = uuid4()
        connection.execute(
            "INSERT INTO operational.offer_cycles "
            "(id,business_id,company_id,recommendation_id,selected_revision_id,"
            "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
            "claim_token,lease_expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'sending',%s)",
            (
                cycle_id,
                business_id,
                company_id,
                recommendation_id,
                revision_id,
                "late-handoff",
                "9" * 64,
                authorization_at - timedelta(minutes=1),
                authorization_at - timedelta(minutes=1),
                authorization_at + timedelta(minutes=4),
            ),
        )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='sending',updated_at=%s,"
            "lease_expires_at=NULL,sending_started_at=%s WHERE id=%s",
            (authorization_at, authorization_at, cycle_id),
        )
        # The delivery was authorized while the recommendation was still open.
        # A later user rejection must not erase an already-authorized handoff.
        connection.execute(
            "INSERT INTO operational.suppression_blocks "
            "(id,business_id,company_id,kind,created_at,effective_at,created_by_user_id,reason) "
            "VALUES (%s,%s,%s,'rejection',%s,%s,%s,'Not relevant')",
            (uuid4(), business_id, company_id, resolution_at, resolution_at, actor_id),
        )
        prospect_id = uuid4()
        connection.execute(
            "INSERT INTO operational.prospects "
            "(id,business_id,company_id,stage,last_active_stage,created_at,updated_at) "
            "VALUES (%s,%s,%s,'closed','contacted',%s,%s)",
            (prospect_id, business_id, company_id, resolution_at, resolution_at),
        )
        connection.execute(
            "UPDATE operational.recommendations SET status='rejected',resolved_at=%s,"
            "resolved_by_user_id=%s,resolution_reason='Not relevant',version=version+1,updated_at=%s "
            "WHERE id=%s",
            (resolution_at, actor_id, resolution_at, recommendation_id),
        )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='confirmed',updated_at=%s,"
            "settled_at=%s,presented_at=%s WHERE id=%s",
            (recorded_at, recorded_at, handoff_at, cycle_id),
        )
        connection.execute(
            "UPDATE operational.recommendations SET first_presented_at=%s,"
            "version=version+1,updated_at=%s WHERE id=%s",
            (handoff_at, recorded_at + timedelta(seconds=1), recommendation_id),
        )
        assert connection.execute(
            "SELECT status,first_presented_at,resolved_at,resolved_by_user_id,"
            "resolution_reason,current_revision_id "
            "FROM operational.recommendations WHERE id=%s",
            (recommendation_id,),
        ).fetchone() == (
            "rejected",
            handoff_at,
            resolution_at,
            actor_id,
            "Not relevant",
            revision_id,
        )
        assert connection.execute(
            "SELECT stage,last_active_stage,version FROM operational.prospects WHERE id=%s",
            (prospect_id,),
        ).fetchone() == ("closed", "contacted", 1)
        assert connection.execute(
            "SELECT kind,cleared_at,version FROM operational.suppression_blocks "
            "WHERE business_id=%s AND company_id=%s",
            (business_id, company_id),
        ).fetchone() == ("rejection", None, 1)


@pytest.mark.parametrize("outcome", ["confirmed", "abandoned"])
def test_unknown_recovery_advances_final_settlement_and_preserves_timeout_history(
    management_database_url, outcome
):
    with psycopg.connect(management_database_url) as connection:
        actor_id, business_id, company_id = _seed_owner_company(connection)
        recommendation_id = _insert_recommendation(connection, business_id, company_id)
        revision_id = _insert_revision(
            connection, business_id, company_id, recommendation_id
        )
        authorized_at = datetime.now(UTC)
        uncertain_at = authorized_at + timedelta(seconds=5)
        actual_handoff_at = authorized_at + timedelta(seconds=10)
        recovered_at = authorized_at + timedelta(days=35)
        cycle_id = uuid4()
        connection.execute(
            "INSERT INTO operational.offer_cycles "
            "(id,business_id,company_id,recommendation_id,selected_revision_id,"
            "idempotency_key,payload_fingerprint,status,created_at,updated_at,"
            "claim_token,lease_expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'preparing',%s,%s,'token',%s)",
            (
                cycle_id,
                business_id,
                company_id,
                recommendation_id,
                revision_id,
                f"late-resolution-{uuid4()}",
                "b" * 64,
                authorized_at,
                authorized_at,
                authorized_at + timedelta(minutes=5),
            ),
        )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='sending',lease_expires_at=NULL,"
            "sending_started_at=%s,updated_at=%s WHERE id=%s",
            (authorized_at, authorized_at, cycle_id),
        )
        connection.execute(
            "UPDATE operational.offer_cycles SET status='unknown',settled_at=%s,"
            "updated_at=%s WHERE id=%s",
            (uncertain_at, uncertain_at, cycle_id),
        )
        timeout_event_id = uuid4()
        connection.execute(
            "INSERT INTO operational.offer_cycle_events "
            "(id,offer_cycle_id,business_id,company_id,event_kind,outcome,recorded_at,payload) "
            "VALUES (%s,%s,%s,%s,'sending_unknown','unknown',%s,%s)",
            (
                timeout_event_id,
                cycle_id,
                business_id,
                company_id,
                uncertain_at,
                Jsonb({"observed_at": uncertain_at.isoformat()}),
            ),
        )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.offer_cycles SET settled_at=%s,updated_at=%s WHERE id=%s",
                (recovered_at, recovered_at, cycle_id),
            )
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.offer_cycles SET status=%s,settled_at=%s,"
                "presented_at=%s,updated_at=%s WHERE id=%s",
                (
                    outcome,
                    authorized_at,
                    actual_handoff_at if outcome == "confirmed" else None,
                    recovered_at,
                    cycle_id,
                ),
            )
        presented_at = actual_handoff_at if outcome == "confirmed" else None
        connection.execute(
            "UPDATE operational.offer_cycles SET status=%s,settled_at=%s,"
            "presented_at=%s,updated_at=%s WHERE id=%s",
            (outcome, recovered_at, presented_at, recovered_at, cycle_id),
        )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO operational.offer_cycle_events "
                "(id,offer_cycle_id,business_id,company_id,event_kind,actor_user_id,"
                "reason,outcome,presented_at,resolved_at,recorded_at) "
                "VALUES (%s,%s,%s,%s,'unknown_resolved',%s,'Wrong resolution time',%s,%s,%s,%s)",
                (
                    uuid4(),
                    cycle_id,
                    business_id,
                    company_id,
                    actor_id,
                    outcome,
                    presented_at,
                    recovered_at - timedelta(seconds=1),
                    recovered_at,
                ),
            )
            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        event_id = uuid4()
        connection.execute(
            "INSERT INTO operational.offer_cycle_events "
            "(id,offer_cycle_id,business_id,company_id,event_kind,actor_user_id,"
            "reason,outcome,presented_at,resolved_at,recorded_at) "
            "VALUES (%s,%s,%s,%s,'unknown_resolved',%s,'Provider result verified',%s,%s,%s,%s)",
            (
                event_id,
                cycle_id,
                business_id,
                company_id,
                actor_id,
                outcome,
                presented_at,
                recovered_at,
                recovered_at,
            ),
        )
        connection.commit()
        assert connection.execute(
            "SELECT status,settled_at,presented_at FROM operational.offer_cycles WHERE id=%s",
            (cycle_id,),
        ).fetchone() == (outcome, recovered_at, presented_at)
        assert connection.execute(
            "SELECT recorded_at,payload FROM operational.offer_cycle_events WHERE id=%s",
            (timeout_event_id,),
        ).fetchone() == (uncertain_at, {"observed_at": uncertain_at.isoformat()})
        assert connection.execute(
            "SELECT actor_user_id,outcome,presented_at,resolved_at FROM operational.offer_cycle_events WHERE id=%s",
            (event_id,),
        ).fetchone() == (actor_id, outcome, presented_at, recovered_at)
        with (
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE operational.offer_cycles SET settled_at=%s,updated_at=%s WHERE id=%s",
                (
                    recovered_at + timedelta(seconds=1),
                    recovered_at + timedelta(seconds=1),
                    cycle_id,
                ),
            )

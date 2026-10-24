from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from huginn.elt.silver.models.lifecycle_facts import LifecycleFacts
from huginn.elt.silver.models.source_extraction import SourceExtraction
from huginn.elt.silver.repositories.source_currentness_repository import (
    PostgresLifecycleRepository,
)
from huginn.management.domain.value_objects.match_status import MatchStatus
from huginn.management.persistence.queries.matches_query import PostgresMatchesQuery
from tests.postgres_harness import provisioned_postgres


@pytest.fixture(scope="module")
def current_evidence_database_url() -> Iterator[str]:
    with provisioned_postgres("huginn_match_evidence_query") as database_url:
        yield database_url


def _user(conn, tag):
    account = conn.execute(
        "INSERT INTO operational.accounts(username,password_hash) VALUES (%s,%s) RETURNING id",
        (f"matches-{tag}-{uuid4()}", "test-only"),
    ).fetchone()[0]
    return conn.execute(
        """INSERT INTO operational.users(account_id,first_name,last_name,email,phone_number,country_of_residence)
           VALUES (%s,'Ada','Lovelace',%s,'+970599000000','Palestine') RETURNING id""",
        (account, f"{uuid4()}@example.test"),
    ).fetchone()[0], account


def test_match_reads_are_owner_scoped_stably_ordered_read_only_and_overview_is_durable(
    management_database_url,
):
    with psycopg.connect(management_database_url) as conn:
        try:
            owner_id, owner_account = _user(conn, "owner")
            other_id, other_account = _user(conn, "other")
            no_history_id, _ = _user(conn, "no-history")
            company_id = conn.execute(
                """INSERT INTO gold.company(domain,name,business_sector,country,company_scale,company_status)
                   VALUES ('matches.test','Matches Co',ARRAY['AI'],'US','0-10','Active') RETURNING id"""
            ).fetchone()[0]
            other_company_id = conn.execute(
                "INSERT INTO gold.company(domain,name) VALUES ('other-matches.test','Other Co') RETURNING id"
            ).fetchone()[0]
            first_id = conn.execute(
                """INSERT INTO operational.match(id,user_id,company_id,status,created_at)
                   VALUES (%s,%s,%s,'new',now()-interval '1 minute') RETURNING id""",
                (uuid4(), owner_id, other_company_id),
            ).fetchone()[0]
            latest_id = conn.execute(
                """INSERT INTO operational.match(id,user_id,company_id,status,created_at)
                   VALUES (%s,%s,%s,'dismissed',now()-interval '1 minute') RETURNING id""",
                (uuid4(), owner_id, company_id),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO operational.match(user_id,company_id) VALUES (%s,%s)",
                (other_id, other_company_id),
            )
            conn.execute(
                """INSERT INTO gold.company_signal(company_id,source,source_stable_id,signal_type,occurred_at)
                   VALUES (%s,'hn',%s,'hiring',now())""",
                (company_id, str(uuid4())),
            )
            conn.execute(
                """INSERT INTO gold.company_signal(company_id,source,source_stable_id,signal_type,occurred_at)
                   VALUES (%s,'hn',%s,'funding',now()-interval '1 day')""",
                (company_id, str(uuid4())),
            )

            old_run = uuid4()
            conn.execute(
                """INSERT INTO ops.matchmaking_runs(id,requester_account_id,request_id,canonical_request,
                     target_kind,cutoff,as_of,state,requested_at,started_at,finished_at,target_count,settled_target_count)
                   VALUES (%s,%s,%s,%s,'user',now(),now(),'succeeded',now()-interval '1 minute',now(),now(),1,1)""",
                (old_run, owner_account, uuid4(), Jsonb({})),
            )
            conn.execute(
                """INSERT INTO ops.matchmaking_run_users(run_id,user_id,ordinal,state,started_at,finished_at,
                     strategies_evaluated,strategies_skipped,unique_candidates_count,created_matches_count,
                     existing_matches_skipped_count)
                   VALUES (%s,%s,0,'succeeded',now(),now(),1,0,0,0,0)""",
                (old_run, owner_id),
            )
            pending_run = uuid4()
            conn.execute(
                """INSERT INTO ops.matchmaking_runs(id,requester_account_id,request_id,canonical_request,
                     target_kind,cutoff,as_of,state,requested_at,target_count,settled_target_count)
                   VALUES (%s,%s,%s,%s,'user',now(),now(),'queued',now(),1,0)""",
                (pending_run, owner_account, uuid4(), Jsonb({})),
            )
            conn.execute(
                "INSERT INTO ops.matchmaking_run_users(run_id,user_id,ordinal,state) VALUES (%s,%s,0,'pending')",
                (pending_run, owner_id),
            )
            other_run = uuid4()
            conn.execute(
                """INSERT INTO ops.matchmaking_runs(id,requester_account_id,request_id,canonical_request,
                     target_kind,cutoff,as_of,state,requested_at,started_at,finished_at,target_count,settled_target_count)
                   VALUES (%s,%s,%s,%s,'user',now(),now(),'succeeded',now(),now(),now(),1,1)""",
                (other_run, other_account, uuid4(), Jsonb({})),
            )
            conn.execute(
                """INSERT INTO ops.matchmaking_run_users(run_id,user_id,ordinal,state,started_at,finished_at,
                     strategies_evaluated,strategies_skipped,unique_candidates_count,created_matches_count,
                     existing_matches_skipped_count)
                   VALUES (%s,%s,0,'succeeded',now(),now(),1,0,9,9,0)""",
                (other_run, other_id),
            )

            query = PostgresMatchesQuery(conn)
            match_count_before = conn.execute(
                "SELECT count(*) FROM operational.match"
            ).fetchone()[0]
            page = query.list_matches(owner_id, None, 0, 2)
            assert [item.id for item in page.items] == sorted(
                [first_id, latest_id], reverse=True
            )
            assert page.has_more is False
            assert (
                query.list_matches(owner_id, MatchStatus("contacted"), 0, 100).items
                == ()
            )
            assert (
                query.list_matches(owner_id, MatchStatus("new"), 0, 10).items[0].id
                == first_id
            )
            detail = query.get_match(owner_id, latest_id)
            assert detail is not None and detail.status == MatchStatus("dismissed")
            assert detail.company.name == "Matches Co"
            assert detail.historical_evidence_available is False
            assert detail.current_source_evidence_available is False
            assert query.get_match(owner_id, uuid4()) is None
            assert query.get_match(other_id, latest_id) is None
            signal_page = query.list_match_signals(owner_id, latest_id, 0, 1)
            assert signal_page.items == ()
            assert signal_page.has_more is False
            assert query.list_match_signals(other_id, latest_id, 0, 1).items == ()

            overview = query.overview_for(owner_id)
            assert overview.has_matches is True
            assert overview.has_active_strategies is False
            assert overview.latest_evaluation is not None
            assert overview.latest_evaluation.state == "pending"
            assert overview.latest_evaluation.created_matches_count is None
            assert (
                query.overview_for(other_id).latest_evaluation.created_matches_count
                == 9
            )
            no_history = query.overview_for(no_history_id)
            assert not no_history.has_matches and no_history.latest_evaluation is None

            conn.execute(
                """UPDATE ops.matchmaking_runs SET state='running',started_at=now(),
                     heartbeat_at=now()-interval '2 minutes',requested_at=now()+interval '1 second'
                   WHERE id=%s""",
                (pending_run,),
            )
            conn.execute(
                """UPDATE ops.matchmaking_run_users SET state='running',started_at=now()
                   WHERE run_id=%s AND user_id=%s""",
                (pending_run, owner_id),
            )
            stale = query.overview_for(owner_id).latest_evaluation
            assert stale is not None and stale.state == "running"
            assert stale.tracking_stale is True
            assert stale.created_matches_count is None

            conn.execute(
                """UPDATE ops.matchmaking_runs SET state='succeeded',started_at=now(),finished_at=now(),
                     settled_target_count=1 WHERE id=%s""",
                (pending_run,),
            )
            conn.execute(
                """UPDATE ops.matchmaking_run_users SET state='succeeded',started_at=now(),finished_at=now(),
                     strategies_evaluated=0,strategies_skipped=0,unique_candidates_count=0,
                     created_matches_count=0,existing_matches_skipped_count=0
                   WHERE run_id=%s AND user_id=%s""",
                (pending_run, owner_id),
            )
            completed = query.overview_for(owner_id).latest_evaluation
            assert completed is not None and completed.state == "succeeded"
            assert completed.created_matches_count == 0
            assert query.list_matches(owner_id, None, 0, 100).items
            assert (
                conn.execute("SELECT count(*) FROM operational.match").fetchone()[0]
                == match_count_before
            )
        finally:
            conn.rollback()


def test_match_signals_read_reconciled_context_and_sort_unknown_dates_last(
    current_evidence_database_url,
):
    event_time = datetime(2025, 1, 2, tzinfo=UTC)
    stable_ids = (f"match-ctx-{uuid4().hex}-dated", f"match-ctx-{uuid4().hex}-unknown")
    domain = f"match-{uuid4().hex}.example.test"
    with psycopg.connect(current_evidence_database_url) as conn:
        owner_id, _ = _user(conn, "current-context")
        company_id = conn.execute(
            "INSERT INTO gold.company(domain,name) VALUES (%s,'Current Co') RETURNING id",
            (domain,),
        ).fetchone()[0]
        match_id = conn.execute(
            "INSERT INTO operational.match(user_id,company_id) VALUES (%s,%s) RETURNING id",
            (owner_id, company_id),
        ).fetchone()[0]
        for stable_id in stable_ids:
            payload = {
                "id": stable_id,
                "website": f"https://{domain}",
                "isHiring": False,
            }
            conn.execute(
                """INSERT INTO bronze.api_ingest
                   (source,stable_id,payload,content_hash,run_id)
                   VALUES ('yc',%s,%s,'content-hash',%s)""",
                (stable_id, Jsonb(payload), uuid4()),
            )
            conn.execute(
                """INSERT INTO silver.resolved_signals
                   (source,source_stable_id,resolved_company_key,company_name_raw,
                    signal_type,key_derivation)
                   VALUES ('yc',%s,%s,'Current Co','hiring','domain_normalized')""",
                (stable_id, domain),
            )
            conn.execute(
                """INSERT INTO gold.company_signal
                   (company_id,source,source_stable_id,signal_type,occurred_at,
                    description)
                   VALUES (%s,'yc',%s,'hiring',%s,'stale Gold label')""",
                (
                    company_id,
                    stable_id,
                    event_time,
                ),
            )
        conn.commit()

    repository = PostgresLifecycleRepository(current_evidence_database_url)
    facts_by_id = {
        stable_ids[0]: event_time,
        stable_ids[1]: None,
    }
    for item in repository.read_inputs("yc"):
        if item.stable_id not in facts_by_id:
            continue
        repository.reconcile(
            item,
            LifecycleFacts(
                listing_state="available",
                hiring_state="false",
                identity_state="consistent",
                reason="test reconciliation",
                explicit_domain=domain,
                occurred_at=facts_by_id[item.stable_id],
                context=SourceExtraction(
                    source="yc",
                    stable_id=item.stable_id,
                    status="captured",
                    source_url=f"https://www.ycombinator.com/companies/{item.stable_id}",
                    normalized_text="Current directory context",
                    source_fields={"stage": "Seed"},
                ),
            ),
        )

    with psycopg.connect(current_evidence_database_url) as conn:
        dated_observation_id = conn.execute(
            """SELECT observation_id FROM gold.current_source_evidence
               WHERE source_stable_id=%s""",
            (stable_ids[0],),
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO operational.match_source_evidence
               (match_id,observation_id,cutoff,as_of)
               VALUES (%s,%s,%s,%s)""",
            (
                match_id,
                dated_observation_id,
                event_time - timedelta(days=1),
                event_time + timedelta(days=1),
            ),
        )
        query = PostgresMatchesQuery(conn)
        detail = query.get_match(owner_id, match_id)
        assert detail is not None
        assert detail.historical_evidence_available is True
        assert detail.current_source_evidence_available is True
        first = query.list_match_signals(owner_id, match_id, 0, 1)
        second = query.list_match_signals(owner_id, match_id, 1, 1)
        assert first.has_more is True
        assert len(first.items) == len(second.items) == 1
        assert first.items[0].source == second.items[0].source == "yc"
        assert first.items[0].signal_type == second.items[0].signal_type == "other"
        assert first.items[0].hiring_state == second.items[0].hiring_state == "false"
        assert (
            first.items[0].evidence_kind
            == second.items[0].evidence_kind
            == "directory_context"
        )
        assert first.items[0].occurred_at == event_time
        assert second.items[0].occurred_at is None
        assert all(
            item.description == "Current directory context"
            for item in (*first.items, *second.items)
        )
        conn.execute(
            """UPDATE bronze.api_ingest
               SET payload=jsonb_set(payload,'{name}',%s)
               WHERE source='yc' AND stable_id = ANY(%s)""",
            (Jsonb("changed"), list(stable_ids)),
        )
        assert query.list_match_signals(owner_id, match_id, 0, 10).items == ()
        stale_detail = query.get_match(owner_id, match_id)
        assert stale_detail is not None
        assert stale_detail.historical_evidence_available is True
        assert stale_detail.current_source_evidence_available is False

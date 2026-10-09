from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from huginn.management.domain.value_objects.match_status import MatchStatus
from huginn.management.persistence.queries.matches_query import PostgresMatchesQuery


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
            signal_new = conn.execute(
                """INSERT INTO gold.company_signal(company_id,source,source_stable_id,signal_type,occurred_at)
                   VALUES (%s,'hn',%s,'hiring',now()) RETURNING id""",
                (company_id, str(uuid4())),
            ).fetchone()[0]
            signal_old = conn.execute(
                """INSERT INTO gold.company_signal(company_id,source,source_stable_id,signal_type,occurred_at)
                   VALUES (%s,'hn',%s,'funding',now()-interval '1 day') RETURNING id""",
                (company_id, str(uuid4())),
            ).fetchone()[0]

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
            assert query.get_match(owner_id, uuid4()) is None
            assert query.get_match(other_id, latest_id) is None
            signal_page = query.list_match_signals(owner_id, latest_id, 0, 1)
            assert [item.id for item in signal_page.items] == [signal_new]
            assert signal_page.has_more is True
            assert (
                query.list_match_signals(owner_id, latest_id, 1, 1).items[0].id
                == signal_old
            )

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

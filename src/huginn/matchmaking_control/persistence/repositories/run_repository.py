"""PostgreSQL queue and result journal; see admin-matchmaking-execution design."""

import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from huginn.management.domain.value_objects.common import Page
from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)
from huginn.matchmaking_control.application.read_models.run_detail import RunDetail
from huginn.matchmaking_control.application.read_models.run_summary import RunSummary
from huginn.matchmaking_control.application.read_models.skipped_strategy_result import (
    SkippedStrategyResult,
)
from huginn.matchmaking_control.application.read_models.user_result import UserResult
from huginn.matchmaking_control.domain.entities.matchmaking_run import MatchmakingRun
from huginn.matchmaking_control.domain.errors.run import (
    ActiveRunConflictError,
    NoEligibleUsersError,
    RequestIdentityConflictError,
    TargetUserDisabledError,
    TargetUserNotFoundError,
    TriggerRateLimitError,
)
from huginn.matchmaking_control.domain.value_objects.requester import Requester
from huginn.matchmaking_control.domain.value_objects.run_state import RunState
from huginn.matchmaking_control.domain.value_objects.run_target import RunTarget
from huginn.matchmaking_control.domain.value_objects.target_state import TargetState


class PostgresRunRepository:
    def __init__(self, connection: DatabaseSession) -> None:
        self._connection = connection

    def admit_run(
        self,
        *,
        requester: Requester,
        request_id: UUID,
        canonical_request: dict[str, object],
        target_kind: str,
        user_id: UUID | None,
        cutoff: datetime,
        as_of: datetime,
        requested_at: datetime,
    ) -> tuple[MatchmakingRun, bool]:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('matchmaking-trigger', 0))"
        ).fetchone()
        existing = self._one(
            "SELECT id, requester_account_id, request_id, canonical_request, target_kind, cutoff, as_of, state, requested_at, started_at, finished_at, worker_id, heartbeat_at, target_count, settled_target_count, safe_error_code "
            "FROM ops.matchmaking_runs WHERE requester_account_id = %s AND request_id = %s",
            (requester.account_id, request_id),
        )
        if existing is not None:
            if _json_value(existing[3]) != canonical_request:
                raise RequestIdentityConflictError(
                    "request id was already used with different input"
                )
            return _run(existing), True

        self._reserve_trigger(requester.account_id, request_id, requested_at)
        if target_kind == "user":
            assert user_id is not None
            row = self._one(
                "SELECT u.id, a.status FROM operational.users u "
                "JOIN operational.accounts a ON a.id = u.account_id WHERE u.id = %s",
                (user_id,),
            )
            if row is None:
                raise TargetUserNotFoundError("target user does not exist")
            if row[1] != "active":
                raise TargetUserDisabledError("target user account is disabled")
            user_ids = (user_id,)
        elif target_kind == "all_eligible":
            found = self._connection.execute(
                "SELECT u.id FROM operational.users u "
                "JOIN operational.accounts a ON a.id = u.account_id "
                "WHERE a.status = 'active' AND EXISTS ("
                "SELECT 1 FROM operational.client_discovery_strategies s "
                "WHERE s.user_id = u.id AND s.is_active = TRUE) ORDER BY u.id"
            ).fetchall()
            user_ids = tuple(row[0] for row in found)
            if not user_ids:
                raise NoEligibleUsersError("there are no eligible users")
        else:
            raise ValueError("invalid target kind")

        active = self._one(
            "SELECT id FROM ops.matchmaking_runs WHERE state IN ('queued', 'running')"
        )
        if active is not None:
            raise ActiveRunConflictError(str(active[0]))
        run_id = uuid4()
        self._execute(
            "INSERT INTO ops.matchmaking_runs (id, requester_account_id, request_id, canonical_request, target_kind, cutoff, as_of, state, requested_at, target_count) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'queued',%s,%s)",
            (
                run_id,
                requester.account_id,
                request_id,
                JsonParameter(canonical_request),
                target_kind,
                cutoff,
                as_of,
                requested_at,
                len(user_ids),
            ),
        )
        for ordinal, target_id in enumerate(user_ids):
            self._execute(
                "INSERT INTO ops.matchmaking_run_users (run_id,user_id,ordinal,state) VALUES (%s,%s,%s,'pending')",
                (run_id, target_id, ordinal),
            )
        run = self.get_run_snapshot(run_id)
        assert run is not None
        return run, False

    def _reserve_trigger(
        self, account_id: UUID, request_id: UUID, now: datetime
    ) -> None:
        # An earlier safe admission refusal can have charged this identity.
        # Retrying it must remain a safe refusal, not a duplicate-key failure.
        if (
            self._one(
                "SELECT 1 FROM ops.matchmaking_trigger_throttle WHERE requester_account_id=%s AND request_id=%s",
                (account_id, request_id),
            )
            is not None
        ):
            return
        recent = self._one(
            "SELECT count(*) FROM ops.matchmaking_trigger_throttle "
            "WHERE requester_account_id = %s AND requested_at > %s - interval '1 hour'",
            (account_id, now),
        )
        assert recent is not None
        if recent[0] >= 10:
            raise TriggerRateLimitError("matchmaking trigger rate limit exceeded")
        self._execute(
            "INSERT INTO ops.matchmaking_trigger_throttle (requester_account_id,request_id,requested_at) VALUES (%s,%s,%s)",
            (account_id, request_id, now),
        )

    def list_runs(
        self, limit: int, offset: int, state: RunState | None = None
    ) -> Page[RunSummary]:
        where = " WHERE state = %s" if state is not None else ""
        params: tuple[Any, ...] = (
            (state.value, limit + 1, offset)
            if state is not None
            else (limit + 1, offset)
        )
        rows = self._connection.execute(
            "SELECT id, requester_account_id, state, requested_at, cutoff, as_of, target_count, settled_target_count "
            "FROM ops.matchmaking_runs"
            + where
            + " ORDER BY requested_at DESC,id DESC LIMIT %s OFFSET %s",
            params,
        ).fetchall()
        return _page(tuple(_summary(row) for row in rows), limit, offset)

    def get_run(self, run_id: UUID) -> RunDetail | None:
        row = self._one(
            "SELECT r.id,r.request_id,r.requester_account_id,r.target_kind,r.state,r.requested_at,r.started_at,r.finished_at,r.cutoff,r.as_of,r.target_count,r.settled_target_count,r.heartbeat_at,r.safe_error_code,"
            "count(*) FILTER (WHERE u.state='succeeded'), count(*) FILTER (WHERE u.state IN ('disabled_user','user_not_found')), count(*) FILTER (WHERE u.state='failed'), count(*) FILTER (WHERE u.state='commit_outcome_unknown'), count(*) FILTER (WHERE u.state='not_executed'),"
            "sum(u.created_matches_count),sum(u.existing_matches_skipped_count),"
            "bool_and(u.state IN ('succeeded','disabled_user','user_not_found')), (r.state='running' AND (r.heartbeat_at IS NULL OR r.heartbeat_at < now() - interval '60 seconds')), "
            "(SELECT active_target.user_id FROM ops.matchmaking_run_users active_target WHERE active_target.run_id=r.id AND active_target.state='running' LIMIT 1) "
            "FROM ops.matchmaking_runs r LEFT JOIN ops.matchmaking_run_users u ON u.run_id=r.id WHERE r.id=%s "
            "GROUP BY r.id",
            (run_id,),
        )
        if row is None:
            return None
        counts_complete = bool(row[21])
        return RunDetail(
            id=row[0],
            request_id=row[1],
            requester_account_id=row[2],
            target_kind=row[3],
            state=RunState(row[4]),
            requested_at=row[5],
            started_at=row[6],
            finished_at=row[7],
            cutoff=row[8],
            as_of=row[9],
            target_count=row[10],
            settled_target_count=row[11],
            heartbeat_at=row[12],
            safe_error_code=row[13],
            succeeded_count=row[14] or 0,
            skipped_count=row[15] or 0,
            failed_count=row[16] or 0,
            uncertain_count=row[17] or 0,
            not_executed_count=row[18] or 0,
            created_matches_count=row[19],
            existing_matches_skipped_count=row[20],
            counts_complete=counts_complete,
            tracking_stale=bool(row[22]),
            current_user_id=row[23],
        )

    def get_run_snapshot(self, run_id: UUID) -> MatchmakingRun | None:
        row = self._one(
            "SELECT id, requester_account_id, request_id, canonical_request, target_kind, cutoff, as_of, state, requested_at, started_at, finished_at, worker_id, heartbeat_at, target_count, settled_target_count, safe_error_code "
            "FROM ops.matchmaking_runs WHERE id=%s",
            (run_id,),
        )
        if row is None:
            return None
        targets = self._connection.execute(
            "SELECT user_id,ordinal,state FROM ops.matchmaking_run_users WHERE run_id=%s ORDER BY ordinal",
            (run_id,),
        ).fetchall()
        return _run(
            row,
            tuple(
                RunTarget(user_id=item[0], ordinal=item[1], state=TargetState(item[2]))
                for item in targets
            ),
        )

    def get_target(self, run_id: UUID, user_id: UUID) -> UserResult | None:
        row = self._one(
            "SELECT run_id,user_id,ordinal,state,started_at,finished_at,strategies_evaluated,strategies_skipped,unique_candidates_count,created_matches_count,existing_matches_skipped_count,safe_reason "
            "FROM ops.matchmaking_run_users WHERE run_id=%s AND user_id=%s",
            (run_id, user_id),
        )
        return None if row is None else _user_result(row)

    def latest_owner_result(self, user_id: UUID) -> dict[str, object] | None:
        row = self._one(
            "SELECT u.state,r.requested_at,u.started_at,u.finished_at,r.cutoff,r.as_of,"
            "(r.state='running' AND u.state IN ('pending','running') AND (r.heartbeat_at IS NULL OR r.heartbeat_at < now() - interval '60 seconds')),"
            "u.strategies_evaluated,u.strategies_skipped,u.created_matches_count,u.existing_matches_skipped_count "
            "FROM ops.matchmaking_run_users u JOIN ops.matchmaking_runs r ON r.id=u.run_id "
            "WHERE u.user_id=%s ORDER BY r.requested_at DESC,r.id DESC LIMIT 1",
            (user_id,),
        )
        if row is None:
            return None
        return {
            "state": TargetState(row[0]),
            "requested_at": row[1],
            "started_at": row[2],
            "finished_at": row[3],
            "cutoff": row[4],
            "as_of": row[5],
            "tracking_stale": row[6],
            "strategies_evaluated": row[7],
            "strategies_skipped": row[8],
            "created_matches_count": row[9],
            "existing_matches_skipped_count": row[10],
        }

    def list_user_results(
        self, run_id: UUID, limit: int, offset: int, state: TargetState | None = None
    ) -> Page[UserResult] | None:
        if (
            self._one("SELECT id FROM ops.matchmaking_runs WHERE id=%s", (run_id,))
            is None
        ):
            return None
        where = " AND state=%s" if state is not None else ""
        params: tuple[Any, ...] = (
            (run_id, state.value, limit + 1, offset)
            if state is not None
            else (run_id, limit + 1, offset)
        )
        rows = self._connection.execute(
            "SELECT run_id,user_id,ordinal,state,started_at,finished_at,strategies_evaluated,strategies_skipped,unique_candidates_count,created_matches_count,existing_matches_skipped_count,safe_reason "
            "FROM ops.matchmaking_run_users WHERE run_id=%s"
            + where
            + " ORDER BY ordinal LIMIT %s OFFSET %s",
            params,
        ).fetchall()
        return _page(tuple(_user_result(row) for row in rows), limit, offset)

    def list_skipped_strategies(
        self, run_id: UUID, user_id: UUID, limit: int, offset: int
    ) -> Page[SkippedStrategyResult] | None:
        if (
            self._one(
                "SELECT 1 FROM ops.matchmaking_run_users WHERE run_id=%s AND user_id=%s",
                (run_id, user_id),
            )
            is None
        ):
            return None
        rows = self._connection.execute(
            "SELECT strategy_id,reason FROM ops.matchmaking_run_skipped_strategies WHERE run_id=%s AND user_id=%s ORDER BY strategy_id LIMIT %s OFFSET %s",
            (run_id, user_id, limit + 1, offset),
        ).fetchall()
        return _page(
            tuple(
                SkippedStrategyResult(strategy_id=row[0], reason=row[1]) for row in rows
            ),
            limit,
            offset,
        )

    def claim_next_run(self, worker_id: UUID, now: datetime) -> MatchmakingRun | None:
        row = self._one(
            "SELECT id, requester_account_id, request_id, canonical_request, target_kind, cutoff, as_of, state, requested_at, started_at, finished_at, worker_id, heartbeat_at, target_count, settled_target_count, safe_error_code "
            "FROM ops.matchmaking_runs WHERE state='queued' ORDER BY requested_at,id FOR NO KEY UPDATE SKIP LOCKED LIMIT 1"
        )
        return None if row is None else _run(row)

    def start_run(self, run_id: UUID, worker_id: UUID, now: datetime) -> bool:
        row = self._one(
            "UPDATE ops.matchmaking_runs SET state='running',worker_id=%s,started_at=%s,heartbeat_at=%s WHERE id=%s AND state='queued' RETURNING id",
            (str(worker_id), now, now, run_id),
        )
        return row is not None

    def start_target(
        self, run_id: UUID, user_id: UUID, worker_id: UUID, now: datetime
    ) -> bool:
        row = self._one(
            "UPDATE ops.matchmaking_run_users u SET state='running',started_at=%s FROM ops.matchmaking_runs r "
            "WHERE u.run_id=%s AND u.user_id=%s AND u.state='pending' AND r.id=u.run_id AND r.state='running' AND r.worker_id=%s RETURNING u.user_id",
            (now, run_id, user_id, str(worker_id)),
        )
        return row is not None

    def acknowledge_target(
        self,
        result: UserResult,
        skipped: tuple[SkippedStrategyResult, ...],
        worker_id: UUID,
        now: datetime,
    ) -> bool:
        row = self._one(
            "UPDATE ops.matchmaking_run_users u SET state=%s,finished_at=%s,strategies_evaluated=%s,strategies_skipped=%s,unique_candidates_count=%s,created_matches_count=%s,existing_matches_skipped_count=%s,safe_reason=%s "
            "FROM ops.matchmaking_runs r WHERE u.run_id=%s AND u.user_id=%s AND u.state='running' AND r.id=u.run_id AND r.worker_id=%s AND r.state='running' RETURNING u.ordinal",
            (
                result.state.value,
                now,
                result.strategies_evaluated,
                result.strategies_skipped,
                result.unique_candidates_count,
                result.created_matches_count,
                result.existing_matches_skipped_count,
                result.safe_reason,
                result.run_id,
                result.user_id,
                str(worker_id),
            ),
        )
        if row is None:
            return False
        for item in skipped:
            self._execute(
                "INSERT INTO ops.matchmaking_run_skipped_strategies (run_id,user_id,strategy_id,reason) VALUES (%s,%s,%s,%s)",
                (result.run_id, result.user_id, item.strategy_id, item.reason),
            )
        self._execute(
            "UPDATE ops.matchmaking_runs SET settled_target_count=settled_target_count+1,heartbeat_at=%s WHERE id=%s AND worker_id=%s AND state='running'",
            (now, result.run_id, str(worker_id)),
        )
        return True

    def pending_targets(self, run_id: UUID, worker_id: UUID) -> tuple[UserResult, ...]:
        rows = self._connection.execute(
            "SELECT u.run_id,u.user_id,u.ordinal,u.state,u.started_at,u.finished_at,u.strategies_evaluated,u.strategies_skipped,u.unique_candidates_count,u.created_matches_count,u.existing_matches_skipped_count,u.safe_reason "
            "FROM ops.matchmaking_run_users u JOIN ops.matchmaking_runs r ON r.id=u.run_id WHERE u.run_id=%s AND r.worker_id=%s AND r.state='running' AND u.state='pending' ORDER BY u.ordinal",
            (run_id, str(worker_id)),
        ).fetchall()
        return tuple(_user_result(row) for row in rows)

    def finish_run(self, run_id: UUID, worker_id: UUID, finished_at: datetime) -> bool:
        row = self._one(
            "UPDATE ops.matchmaking_runs r SET state=CASE WHEN NOT EXISTS (SELECT 1 FROM ops.matchmaking_run_users u WHERE u.run_id=r.id AND u.state NOT IN ('succeeded','disabled_user','user_not_found')) THEN 'succeeded' ELSE 'completed_with_errors' END,finished_at=%s,heartbeat_at=%s "
            "WHERE r.id=%s AND r.worker_id=%s AND r.state='running' AND r.settled_target_count=r.target_count RETURNING r.id",
            (finished_at, finished_at, run_id, str(worker_id)),
        )
        return row is not None

    def reconcile_run(
        self, run_id: UUID, worker_id: UUID, finished_at: datetime
    ) -> bool:
        owner = self._one(
            "SELECT id FROM ops.matchmaking_runs WHERE id=%s AND ((state='running' AND worker_id=%s) OR (state='queued' AND worker_id IS NULL)) FOR NO KEY UPDATE",
            (run_id, str(worker_id)),
        )
        if owner is None:
            return False
        self._execute(
            "UPDATE ops.matchmaking_run_users SET state=CASE WHEN state='running' THEN 'commit_outcome_unknown' ELSE 'not_executed' END,finished_at=%s,safe_reason=CASE WHEN state='running' THEN 'commit_outcome_unknown' ELSE NULL END WHERE run_id=%s AND state IN ('pending','running')",
            (finished_at, run_id),
        )
        self._execute(
            "UPDATE ops.matchmaking_runs SET state='interrupted',worker_id=COALESCE(worker_id,%s),finished_at=%s,heartbeat_at=%s,settled_target_count=target_count,safe_error_code='executor_interrupted' WHERE id=%s AND ((state='running' AND worker_id=%s) OR (state='queued' AND worker_id IS NULL))",
            (str(worker_id), finished_at, finished_at, run_id, str(worker_id)),
        )
        return True

    def heartbeat(self, run_id: UUID, worker_id: UUID, now: datetime) -> bool:
        return (
            self._one(
                "UPDATE ops.matchmaking_runs SET heartbeat_at=%s WHERE id=%s AND worker_id=%s AND state='running' RETURNING id",
                (now, run_id, str(worker_id)),
            )
            is not None
        )

    def _one(self, query: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
        return self._connection.execute(query, params).fetchone()

    def _execute(self, query: str, params: tuple[Any, ...]) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)


def _json_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _run(row: tuple[Any, ...], targets: tuple[RunTarget, ...] = ()) -> MatchmakingRun:
    return MatchmakingRun(
        id=row[0],
        requester=Requester(account_id=row[1]),
        request_id=row[2],
        canonical_request=_json_value(row[3]),
        target_kind=row[4],
        cutoff=row[5],
        as_of=row[6],
        state=RunState(row[7]),
        requested_at=row[8],
        started_at=row[9],
        finished_at=row[10],
        worker_id=row[11],
        heartbeat_at=row[12],
        target_count=row[13],
        settled_target_count=row[14],
        safe_error_code=row[15],
        targets=targets,
    )


def _summary(row: tuple[Any, ...]) -> RunSummary:
    return RunSummary(
        id=row[0],
        requester_account_id=row[1],
        state=RunState(row[2]),
        requested_at=row[3],
        cutoff=row[4],
        as_of=row[5],
        target_count=row[6],
        settled_target_count=row[7],
    )


def _user_result(row: tuple[Any, ...]) -> UserResult:
    return UserResult(
        run_id=row[0],
        user_id=row[1],
        ordinal=row[2],
        state=TargetState(row[3]),
        started_at=row[4],
        finished_at=row[5],
        strategies_evaluated=row[6],
        strategies_skipped=row[7],
        unique_candidates_count=row[8],
        created_matches_count=row[9],
        existing_matches_skipped_count=row[10],
        safe_reason=row[11],
    )


def _page(items: tuple[Any, ...], limit: int, offset: int) -> Page[Any]:
    return Page(
        items=items[:limit], limit=limit, offset=offset, has_more=len(items) > limit
    )

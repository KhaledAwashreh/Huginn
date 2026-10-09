"""Grouped integration coverage for the managed pipeline's durable boundaries."""

from __future__ import annotations

import sys
import threading
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from huginn.elt.gold.company import CompanyWriter
from huginn.elt.gold.models import DomainNormalizedSignal
from huginn.elt.gold.repositories.company_repository import PostgresCompanyRepository
from huginn.elt.stage_runner import Stage, run_stages
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.ops.job_runs import JobRunStatus, finish_job_run, start_job_run
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter
from huginn.pipeline_control.application.read_models.tracking_context import (
    TrackingContext,
)
from huginn.pipeline_control.application.requests.list_invocation_companies_request import (
    ListInvocationCompaniesRequest,
)
from huginn.pipeline_control.application.services.list_invocation_companies_service import (
    ListInvocationCompaniesService,
)
from huginn.pipeline_control.domain.value_objects.stage_plan import SUPPORTED_STAGE_PLAN
from huginn.pipeline_control.infrastructure.invocation_job_run_writer import (
    InvocationJobRunWriter,
)
from huginn.pipeline_control.infrastructure.postgres_execution_guard import (
    PostgresExecutionGuard,
)
from huginn.pipeline_control.infrastructure.process_supervisor import (
    ProcessExecutorSupervisor,
    group_members,
    new_execution_owner,
)
from huginn.pipeline_control.persistence.database.unit_of_work import (
    PostgresPipelineUnitOfWork,
)
from huginn.pipeline_control.persistence.queries.invocation_company_reader import (
    PostgresInvocationCompanyReader,
)
from huginn.pipeline_control.persistence.repositories.execution_guard import (
    PostgresExecutionGuardRepository,
)


def _create_invocation(
    database_url: str,
    *,
    state: str = "queued",
    tracking_state: str = "tracked",
    worker_id: str | None = None,
) -> tuple[UUID, UUID]:
    account_id, invocation_id = uuid4(), uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO operational.accounts (id, username, password_hash) "
            "VALUES (%s, %s, 'integration-placeholder')",
            (account_id, f"pipeline-integration-{account_id.hex}"),
        )
        connection.execute(
            "INSERT INTO ops.pipeline_invocations "
            "(id, requester_account_id, request_id, state, requested_at, plan, "
            "worker_id, company_results_tracking_state) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                invocation_id,
                account_id,
                uuid4(),
                state,
                datetime.now(UTC),
                Jsonb(SUPPORTED_STAGE_PLAN.to_json()),
                worker_id,
                tracking_state,
            ),
        )
    return account_id, invocation_id


def _delete_invocation(
    database_url: str,
    account_id: UUID,
    invocation_id: UUID,
    *,
    domains: tuple[str, ...] = (),
    source_stable_ids: tuple[str, ...] = (),
) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "DELETE FROM ops.pipeline_company_results WHERE invocation_id = %s",
            (invocation_id,),
        )
        connection.execute(
            "DELETE FROM ops.pipeline_invocation_events WHERE invocation_id = %s",
            (invocation_id,),
        )
        connection.execute(
            "DELETE FROM ops.job_runs WHERE invocation_id = %s AND execution_kind = 'source'",
            (invocation_id,),
        )
        connection.execute(
            "DELETE FROM ops.job_runs WHERE invocation_id = %s", (invocation_id,)
        )
        if domains:
            connection.execute(
                "DELETE FROM gold.company WHERE domain = ANY(%s)", (list(domains),)
            )
        if source_stable_ids:
            connection.execute(
                "DELETE FROM silver.resolved_signals WHERE source_stable_id = ANY(%s)",
                (list(source_stable_ids),),
            )
        connection.execute(
            "UPDATE ops.pipeline_execution_guard SET invocation_id = NULL "
            "WHERE singleton = 1 AND active = FALSE AND invocation_id = %s",
            (invocation_id,),
        )
        connection.execute(
            "DELETE FROM ops.pipeline_invocations WHERE id = %s", (invocation_id,)
        )
        connection.execute(
            "DELETE FROM operational.accounts WHERE id = %s", (account_id,)
        )


def test_competing_workers_skip_locked_claim_and_restart_does_not_replay_running_work(
    integration_database_url: str,
) -> None:
    account_id, invocation_id = _create_invocation(integration_database_url)
    factory = ManagementConnectionFactory(integration_database_url)
    guard = PostgresExecutionGuard(factory)
    owner = new_execution_owner(invocation_id)
    first = PostgresPipelineUnitOfWork(factory)
    second = PostgresPipelineUnitOfWork(factory)
    first.__enter__()
    second.__enter__()
    try:
        claimed = first.invocations.claim_queued(str(owner.owner_id), datetime.now(UTC))
        assert claimed is not None and claimed.id == invocation_id
        assert (
            second.invocations.claim_queued("competing-worker", datetime.now(UTC))
            is None
        )

        assert guard.acquire(owner)
        assert first.invocations.mark_running(
            invocation_id, str(owner.owner_id), datetime.now(UTC)
        )
        first.commit()
        assert (
            second.invocations.claim_queued("restarted-worker", datetime.now(UTC))
            is None
        )

        guard.close()
        restarted_guard = PostgresExecutionGuard(factory)
        try:
            assert restarted_guard.acquire(new_execution_owner(invocation_id)) is False
        finally:
            restarted_guard.close()
        active = PostgresExecutionGuardRepository(second.connection).get_active()
        assert active is not None and active[3] and active[0] == owner
    finally:
        second.__exit__(None, None, None)
        first.__exit__(None, None, None)
        guard.close()
        cleanup = factory.connect()
        try:
            repository = PostgresExecutionGuardRepository(cleanup)
            active = repository.get_active()
            if active is not None and active[3] and active[0] == owner:
                assert repository.release(owner.owner_id)
                cleanup.commit()
        finally:
            cleanup.close()
        _delete_invocation(integration_database_url, account_id, invocation_id)


def _fixture_stages(
    database_url: str,
    invocation_id: UUID,
    *,
    fail_source: str | None = None,
) -> list[Stage]:
    def stage_for(descriptor) -> Stage:
        def run() -> int:
            return 1

        def run_managed(context: TrackingContext) -> int:
            for source_name in descriptor.source_children:
                source_writer = InvocationJobRunWriter(
                    PostgresJobRunWriter(database_url), context, source=True
                )
                source = start_job_run(source_name)
                source_writer.write(source)
                terminal = (
                    JobRunStatus.FAILED
                    if source_name == fail_source
                    else JobRunStatus.SUCCEEDED
                )
                source_writer.write(
                    finish_job_run(
                        source,
                        terminal,
                        error="fixture source failure"
                        if terminal == JobRunStatus.FAILED
                        else None,
                    )
                )
            if (
                fail_source == descriptor.name
                or fail_source in descriptor.source_children
            ):
                raise RuntimeError("aggregate source failure")
            return len(descriptor.source_children) or 1

        return Stage(
            descriptor.name,
            run,
            depends_on=descriptor.dependencies,
            run_managed=run_managed,
        )

    return [stage_for(descriptor) for descriptor in SUPPORTED_STAGE_PLAN.stages]


def test_supported_nine_stage_graph_preserves_hn_yc_eu_lineage_and_failure_policy(
    integration_database_url: str,
) -> None:
    expected_names = tuple(stage.name for stage in SUPPORTED_STAGE_PLAN.stages)
    assert expected_names == (
        "ingestion",
        "ingestion.eu_startups",
        "silver.hn_staging",
        "silver.yc_staging",
        "silver.eu_startups_staging",
        "silver.signal_resolution",
        "silver.manual_review",
        "gold.company",
        "gold.company_signal",
    )
    success_account_id, success_id = _create_invocation(
        integration_database_url, state="running"
    )
    failure_account_id = None
    writer = PostgresJobRunWriter(integration_database_url)
    try:
        success = run_stages(
            _fixture_stages(integration_database_url, success_id),
            writer,
            invocation_id=success_id,
            strict_tracking=True,
        )
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "UPDATE ops.pipeline_invocations SET state = 'succeeded', finished_at = %s "
                "WHERE id = %s",
                (datetime.now(UTC), success_id),
            )
        failure_account_id, failure_id = _create_invocation(
            integration_database_url, state="running"
        )
        failed = run_stages(
            _fixture_stages(integration_database_url, failure_id, fail_source="hn"),
            writer,
            invocation_id=failure_id,
            strict_tracking=True,
        )
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "UPDATE ops.pipeline_invocations SET state = 'failed', finished_at = %s "
                "WHERE id = %s",
                (datetime.now(UTC), failure_id),
            )
        assert tuple(success) == expected_names
        assert set(success.values()) == {JobRunStatus.SUCCEEDED}
        assert failed["ingestion"] == JobRunStatus.FAILED
        assert failed["ingestion.eu_startups"] == JobRunStatus.SUCCEEDED
        assert failed["silver.eu_startups_staging"] == JobRunStatus.SUCCEEDED
        assert failed["silver.hn_staging"] == JobRunStatus.SKIPPED
        assert failed["silver.yc_staging"] == JobRunStatus.SKIPPED
        assert failed["silver.signal_resolution"] == JobRunStatus.SKIPPED
        assert failed["silver.manual_review"] == JobRunStatus.SKIPPED
        assert failed["gold.company"] == JobRunStatus.SKIPPED
        assert failed["gold.company_signal"] == JobRunStatus.SKIPPED

        with psycopg.connect(integration_database_url) as connection:
            source_rows = connection.execute(
                "SELECT source, status, invocation_id, parent_job_run_id, execution_kind "
                "FROM ops.job_runs WHERE invocation_id = %s AND execution_kind = 'source' "
                "ORDER BY source",
                (success_id,),
            ).fetchall()
            stage_rows = connection.execute(
                "SELECT id, source, status FROM ops.job_runs "
                "WHERE invocation_id = %s AND execution_kind = 'stage'",
                (success_id,),
            ).fetchall()
            failed_sources = connection.execute(
                "SELECT source, status, parent_job_run_id FROM ops.job_runs "
                "WHERE invocation_id = %s AND execution_kind = 'source' ORDER BY source",
                (failure_id,),
            ).fetchall()

        assert [(row[0], row[1]) for row in source_rows] == [
            ("eu_startups", "succeeded"),
            ("hn", "succeeded"),
            ("yc", "succeeded"),
        ]
        stage_ids = {source: stage_id for stage_id, source, _ in stage_rows}
        assert len(stage_ids) == len(expected_names)
        assert {(source, parent_id) for source, _, _, parent_id, _ in source_rows} == {
            ("hn", stage_ids["ingestion"]),
            ("yc", stage_ids["ingestion"]),
            ("eu_startups", stage_ids["ingestion.eu_startups"]),
        }
        assert all(row[4] == "source" for row in source_rows)
        assert [(row[0], row[1]) for row in failed_sources] == [
            ("eu_startups", "succeeded"),
            ("hn", "failed"),
            ("yc", "succeeded"),
        ]
        assert all(row[2] is not None for row in failed_sources)
    finally:
        _delete_invocation(integration_database_url, success_account_id, success_id)
        if failure_account_id is not None:
            _delete_invocation(integration_database_url, failure_account_id, failure_id)


class _FilteredCompanyRepository(PostgresCompanyRepository):
    def __init__(
        self,
        database_url: str,
        domains: tuple[str, ...],
        *,
        fail_after: int | None = None,
    ):
        super().__init__(database_url)
        self._domains = set(domains)
        self._fail_after = fail_after
        self._attributions = 0

    def read_domain_normalized_signals(self) -> list[DomainNormalizedSignal]:
        return [
            signal
            for signal in super().read_domain_normalized_signals()
            if signal.domain in self._domains
        ]

    def record_company_result(self, invocation_id, stage_job_run_id, company_id):
        super().record_company_result(invocation_id, stage_job_run_id, company_id)
        self._attributions += 1
        if self._fail_after == self._attributions:
            raise RuntimeError("injected company attribution failure")


def test_gold_batch_attribution_rolls_back_retries_and_pages_by_invocation(
    integration_database_url: str,
) -> None:
    suffix = uuid4().hex
    domains = (f"pipeline-{suffix}-a.example", f"pipeline-{suffix}-b.example")
    stable_ids = (f"pipeline-{suffix}-signal-a", f"pipeline-{suffix}-signal-b")
    account_id, invocation_id = _create_invocation(
        integration_database_url, state="running"
    )
    gold_job_id = uuid4()
    context = TrackingContext(invocation_id, gold_job_id, "gold.company")
    try:
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "INSERT INTO ops.job_runs "
                "(id, source, status, rows_written, invocation_id, execution_kind) "
                "VALUES (%s, 'gold.company', 'running', 0, %s, 'stage')",
                (gold_job_id, invocation_id),
            )
            for offset, (domain, stable_id) in enumerate(
                zip(domains, stable_ids, strict=True)
            ):
                connection.execute(
                    "INSERT INTO silver.resolved_signals "
                    "(source_stable_id, source, resolved_company_key, company_name_raw, "
                    "signal_type, key_derivation, industries, team_size, resolved_at) "
                    "VALUES (%s, 'yc', %s, %s, 'other', 'domain_normalized', "
                    "ARRAY['Software'], 8, %s)",
                    (
                        stable_id,
                        domain,
                        f"Pipeline Fixture {offset}",
                        datetime.now(UTC),
                    ),
                )

        failing = CompanyWriter(
            _FilteredCompanyRepository(integration_database_url, domains, fail_after=2)
        )
        with pytest.raises(RuntimeError, match="injected company attribution failure"):
            failing.write_all(context)
        with psycopg.connect(integration_database_url) as connection:
            rolled_back = connection.execute(
                "SELECT count(*) FROM gold.company WHERE domain = ANY(%s)",
                (list(domains),),
            ).fetchone()[0]
            rolled_back_results = connection.execute(
                "SELECT count(*) FROM ops.pipeline_company_results WHERE invocation_id = %s",
                (invocation_id,),
            ).fetchone()[0]
        assert rolled_back == 0
        assert rolled_back_results == 0

        writer = CompanyWriter(
            _FilteredCompanyRepository(integration_database_url, domains)
        )
        assert writer.write_all(context) == 2
        assert writer.write_all(context) == 2
        reader = ListInvocationCompaniesService(
            PostgresInvocationCompanyReader(
                ManagementConnectionFactory(integration_database_url)
            )
        )
        first = reader.execute(ListInvocationCompaniesRequest(invocation_id, 1, 0))
        second = reader.execute(ListInvocationCompaniesRequest(invocation_id, 1, 1))
        assert first.tracking_state == second.tracking_state == "tracked"
        assert first.total_count == second.total_count == 2
        assert first.has_more and not second.has_more
        assert first.items[0].id < second.items[0].id
        assert {first.items[0].domain, second.items[0].domain} == set(domains)
        assert {
            first.items[0].stage_job_run_id,
            second.items[0].stage_job_run_id,
        } == {gold_job_id}
        assert set(vars(first.items[0])) == {
            "id",
            "name",
            "domain",
            "business_sector",
            "country",
            "company_scale",
            "company_status",
            "stage_job_run_id",
        }
        with psycopg.connect(integration_database_url) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM ops.pipeline_company_results WHERE invocation_id = %s",
                    (invocation_id,),
                ).fetchone()[0]
                == 2
            )
    finally:
        _delete_invocation(
            integration_database_url,
            account_id,
            invocation_id,
            domains=domains,
            source_stable_ids=stable_ids,
        )


def test_guard_loss_mid_child_fetch_kills_the_entire_executor_process_group(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "fetch-child.pid"
    script = (
        "import json,subprocess,sys,time; "
        "from dataclasses import asdict; "
        "from huginn.pipeline_control.infrastructure.process_supervisor import current_identity; "
        "print(json.dumps(asdict(current_identity())),flush=True); "
        "assert sys.stdin.readline() == 'GO\\n'; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        f"open({str(pid_file)!r},'w').write(str(child.pid)); "
        "time.sleep(60)"
    )

    class LostGuard:
        def __init__(self):
            self.calls = 0
            self.identity = None

        def attach_executor(self, _owner_id, identity):
            self.identity = identity

        def heartbeat(self, _owner_id):
            self.calls += 1
            if self.calls > 1 and pid_file.exists():
                raise RuntimeError("guard connection lost")

    guard = LostGuard()
    supervisor = ProcessExecutorSupervisor(
        command=(sys.executable, "-c", script),
        heartbeat_seconds=0.05,
        termination_grace_seconds=0.2,
    )
    owner = new_execution_owner(None)
    failures = []

    def execute() -> None:
        try:
            supervisor.run(owner, guard)
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=execute)
    worker.start()
    deadline = time.monotonic() + 5
    while not pid_file.exists() and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert pid_file.exists()
    child_pid = int(pid_file.read_text())
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert failures
    assert guard.identity is not None
    assert group_members(guard.identity.pid) == ()
    child_stat = Path(f"/proc/{child_pid}/stat")
    assert (
        not child_stat.exists()
        or child_stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"
    )


def test_unknown_settlement_commit_is_resolved_by_durable_readback() -> None:
    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class SharedState:
        lock_held = False
        active = False
        owner = None
        execution_id = None
        invocation_id = None
        host = None
        supervisor_pid = None
        supervisor_started_at = None
        fail_commit_once = False

    state = SharedState()

    class Session:
        def __init__(self):
            self.owns_lock = False

        class _Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, _query, _params=()):
                return None

        def cursor(self):
            return self._Cursor()

        def execute(self, query, params=()):
            if "pg_try_advisory_lock" in query:
                if state.lock_held:
                    return Result((False,))
                state.lock_held = self.owns_lock = True
                return Result((True,))
            if "pg_advisory_unlock" in query:
                state.lock_held = self.owns_lock = False
                return Result((True,))
            if "pg_locks" in query:
                return Result((self.owns_lock,))
            if "UPDATE ops.pipeline_execution_guard SET owner_id" in query:
                (
                    state.owner,
                    state.execution_id,
                    state.invocation_id,
                    state.host,
                    state.supervisor_pid,
                    state.supervisor_started_at,
                ) = params[:6]
                state.active = True
                return Result((1,))
            if "SELECT owner_id, execution_id" in query:
                return Result(
                    (
                        state.owner,
                        state.execution_id,
                        state.invocation_id,
                        state.host,
                        state.supervisor_pid,
                        state.supervisor_started_at,
                        None,
                        None,
                        datetime.now(UTC),
                        None,
                        state.active,
                    )
                )
            if "UPDATE ops.pipeline_execution_guard SET active = FALSE" in query:
                state.active = False
                return Result((1,))
            return Result(None)

        def commit(self):
            if state.fail_commit_once:
                state.fail_commit_once = False
                raise OSError("commit acknowledgement lost")

        def rollback(self):
            pass

        def close(self):
            if self.owns_lock:
                state.lock_held = self.owns_lock = False

    class Factory:
        def connect(self):
            return Session()

    guard = PostgresExecutionGuard(Factory())
    owner = new_execution_owner(None)
    assert guard.acquire(owner)
    state.fail_commit_once = True

    assert guard.settle(owner, "succeeded") is True

    assert state.active is False
    assert state.lock_held is False


@pytest.mark.parametrize(
    "exit_code, expected", [(0, "succeeded"), (1, "failed"), (3, "interrupted")]
)
def test_actual_worker_supervised_child_observes_running_and_persisted_identity_before_work(
    integration_database_url, exit_code, expected
):
    from huginn.pipeline_control.application.requests.run_queued_invocation_request import (
        RunQueuedInvocationRequest,
    )
    from huginn.pipeline_control.application.services.run_queued_invocation_service import (
        RunQueuedInvocationService,
    )

    account_id, invocation_id = _create_invocation(integration_database_url)
    factory = ManagementConnectionFactory(integration_database_url)
    script = """import json,sys,psycopg
from dataclasses import asdict
from huginn.pipeline_control.infrastructure.process_supervisor import current_identity
identity=current_identity()
print(json.dumps(asdict(identity)),flush=True)
assert sys.stdin.readline() == 'GO\\n'
with psycopg.connect(sys.argv[1]) as connection:
    row=connection.execute('SELECT i.state,g.active,g.executor_pid,g.executor_started_at FROM ops.pipeline_invocations i JOIN ops.pipeline_execution_guard g ON g.invocation_id=i.id WHERE i.id=%s',(sys.argv[2],)).fetchone()
    assert row == ('running',True,identity.pid,identity.started_at), row
raise SystemExit(int(sys.argv[3]))
"""
    supervisor = ProcessExecutorSupervisor(
        command=(
            sys.executable,
            "-c",
            script,
            integration_database_url,
            str(invocation_id),
            str(exit_code),
        ),
        heartbeat_seconds=0.05,
    )
    service = RunQueuedInvocationService(
        lambda: PostgresPipelineUnitOfWork(factory),
        lambda: PostgresExecutionGuard(factory),
        supervisor,
        new_execution_owner,
    )
    try:
        response = service.execute(RunQueuedInvocationRequest("fixture-worker"))
        assert response.invocation_id == invocation_id
        assert response.status == expected
        with psycopg.connect(integration_database_url) as connection:
            state, started, finished = connection.execute(
                "SELECT state,started_at,finished_at FROM ops.pipeline_invocations WHERE id=%s",
                (invocation_id,),
            ).fetchone()
            assert state == expected and started is not None and finished is not None
            assert connection.execute(
                "SELECT active FROM ops.pipeline_execution_guard"
            ).fetchone() == (False,)
            kinds = [
                row[0]
                for row in connection.execute(
                    "SELECT kind FROM ops.pipeline_invocation_events WHERE invocation_id=%s ORDER BY sequence",
                    (invocation_id,),
                ).fetchall()
            ]
            assert kinds == ["invocation_started", f"invocation_{expected}"]
        assert service.execute(RunQueuedInvocationRequest("restart")).status == "idle"
    finally:
        _delete_invocation(integration_database_url, account_id, invocation_id)


def _stopped_owner(invocation_id):
    import subprocess
    from dataclasses import replace

    from huginn.pipeline_control.infrastructure.process_supervisor import process_start

    previous = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.05)"])
    started_at = process_start(previous.pid)
    previous.wait(timeout=2)
    return replace(
        new_execution_owner(invocation_id),
        supervisor_pid=previous.pid,
        supervisor_started_at=started_at,
    )


@pytest.mark.parametrize("mode", ("managed", "standalone"))
def test_stopped_prestart_owner_can_reconcile_a_queued_invocation_without_fabricating_execution(
    integration_database_url,
    mode,
):
    from huginn.pipeline_control.application.requests.reconcile_invocation_request import (
        ReconcileInvocationRequest,
    )
    from huginn.pipeline_control.application.services.reconcile_invocation_service import (
        ReconcileInvocationService,
    )
    from huginn.pipeline_control.persistence.queries.invocation_reader import (
        PostgresInvocationReader,
    )

    factory = ManagementConnectionFactory(integration_database_url)
    account_id, invocation_id = _create_invocation(integration_database_url)
    owner = _stopped_owner(invocation_id if mode == "managed" else None)
    guard = PostgresExecutionGuard(factory)
    try:
        assert guard.acquire(owner)
        guard.close()
        if mode == "managed":
            assert (
                ReconcileInvocationService(guard, ProcessExecutorSupervisor())
                .execute(ReconcileInvocationRequest(invocation_id, True))
                .status
                == "interrupted"
            )
        else:
            from huginn.pipeline_control.application.requests.reconcile_execution_request import (
                ReconcileExecutionRequest,
            )
            from huginn.pipeline_control.application.services.reconcile_execution_service import (
                ReconcileExecutionService,
            )

            assert (
                ReconcileExecutionService(guard, ProcessExecutorSupervisor())
                .execute(ReconcileExecutionRequest(owner.execution_id, True))
                .status
                == "interrupted"
            )
        detail = PostgresInvocationReader(factory).get(invocation_id)
        assert detail.state == ("interrupted" if mode == "managed" else "queued")
        assert all(
            stage.state == ("not_executed" if mode == "managed" else "pending")
            and stage.job_run_id is None
            for stage in detail.stages
        )
        with psycopg.connect(integration_database_url) as connection:
            assert connection.execute(
                "SELECT active FROM ops.pipeline_execution_guard"
            ).fetchone() == (False,)
    finally:
        guard.close()
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "UPDATE ops.pipeline_execution_guard SET active=FALSE WHERE owner_id=%s",
                (owner.owner_id,),
            )
        _delete_invocation(integration_database_url, account_id, invocation_id)


def test_live_guard_connection_loss_stops_child_keeps_blocker_and_requires_stopped_owner_recovery(
    integration_database_url, tmp_path
):
    from huginn.pipeline_control.application.errors.execution import (
        TrackingUncertainError,
    )
    from huginn.pipeline_control.application.requests.reconcile_invocation_request import (
        ReconcileInvocationRequest,
    )
    from huginn.pipeline_control.application.requests.run_queued_invocation_request import (
        RunQueuedInvocationRequest,
    )
    from huginn.pipeline_control.application.services.reconcile_invocation_service import (
        ReconcileInvocationService,
    )
    from huginn.pipeline_control.application.services.run_queued_invocation_service import (
        RunQueuedInvocationService,
    )
    from huginn.pipeline_control.persistence.queries.invocation_reader import (
        PostgresInvocationReader,
    )

    factory = ManagementConnectionFactory(integration_database_url)
    account_id, invocation_id = _create_invocation(integration_database_url)
    prior_owner = _stopped_owner(None)
    marker = tmp_path / "executor-started"
    script = """import json,sys,time,psycopg
from dataclasses import asdict
from huginn.pipeline_control.infrastructure.process_supervisor import current_identity
identity=current_identity()
print(json.dumps(asdict(identity)),flush=True)
assert sys.stdin.readline() == 'GO\\n'
with psycopg.connect(sys.argv[1]) as connection:
    connection.execute("INSERT INTO ops.job_runs (source,status,rows_written,invocation_id,execution_kind) VALUES ('ingestion','succeeded',0,%s,'stage')",(sys.argv[2],))
open(sys.argv[3],'w').write(str(identity.pid))
time.sleep(60)
"""

    class LostGuard(PostgresExecutionGuard):
        def __init__(self, factory):
            super().__init__(factory)
            self.calls = 0

        def heartbeat(self, owner_id):
            self.calls += 1
            if self.calls > 1 and marker.exists():
                self._connection.close()
                raise TrackingUncertainError("execution_guard_lost")
            super().heartbeat(owner_id)

    guard = LostGuard(factory)
    from dataclasses import replace

    service = RunQueuedInvocationService(
        lambda: PostgresPipelineUnitOfWork(factory),
        lambda: guard,
        ProcessExecutorSupervisor(
            command=(
                sys.executable,
                "-c",
                script,
                integration_database_url,
                str(invocation_id),
                str(marker),
            ),
            heartbeat_seconds=0.2,
            termination_grace_seconds=0.2,
        ),
        lambda identity: replace(prior_owner, invocation_id=identity),
    )
    try:
        with pytest.raises(RuntimeError, match="settlement_unavailable"):
            service.execute(RunQueuedInvocationRequest("fixture-loss"))
        assert marker.exists()
        child_pid = int(marker.read_text())
        assert not Path(f"/proc/{child_pid}").exists()
        detail = PostgresInvocationReader(factory).get(invocation_id)
        assert detail.state == "running"
        busy = PostgresExecutionGuard(factory)
        assert busy.acquire(new_execution_owner(None)) is False
        busy.close()
        recovery = PostgresExecutionGuard(factory)
        result = ReconcileInvocationService(
            recovery, ProcessExecutorSupervisor()
        ).execute(ReconcileInvocationRequest(invocation_id, True))
        assert result.status == "interrupted"
        detail = PostgresInvocationReader(factory).get(invocation_id)
        assert detail.stages[0].state == "succeeded"
        assert all(stage.state == "not_executed" for stage in detail.stages[1:])
        with psycopg.connect(integration_database_url) as connection:
            assert connection.execute(
                "SELECT active FROM ops.pipeline_execution_guard"
            ).fetchone() == (False,)
    finally:
        guard.close()
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "UPDATE ops.pipeline_execution_guard SET active=FALSE WHERE owner_id=%s",
                (prior_owner.owner_id,),
            )
        _delete_invocation(integration_database_url, account_id, invocation_id)


def test_supervisor_process_crash_leaves_durable_blocker_until_real_orphan_group_is_stopped(
    integration_database_url, tmp_path
):
    import os
    import signal
    import subprocess

    from huginn.pipeline_control.application.requests.reconcile_invocation_request import (
        ReconcileInvocationRequest,
    )
    from huginn.pipeline_control.application.services.reconcile_invocation_service import (
        ReconcileInvocationService,
    )

    account_id, invocation_id = _create_invocation(integration_database_url)
    marker = tmp_path / "orphan-executor.pid"
    child_script = tmp_path / "trusted-fixture-child.py"
    child_script.write_text("""import json,sys,time
from dataclasses import asdict
from huginn.pipeline_control.infrastructure.process_supervisor import current_identity
identity=current_identity()
print(json.dumps(asdict(identity)),flush=True)
assert sys.stdin.readline()=='GO\\n'
open(sys.argv[1],'w').write(str(identity.pid))
time.sleep(60)
""")
    parent_script = tmp_path / "fixture-supervisor.py"
    parent_script.write_text("""import sys
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.pipeline_control.application.services.run_queued_invocation_service import RunQueuedInvocationService
from huginn.pipeline_control.application.requests.run_queued_invocation_request import RunQueuedInvocationRequest
from huginn.pipeline_control.infrastructure.postgres_execution_guard import PostgresExecutionGuard
from huginn.pipeline_control.infrastructure.process_supervisor import ProcessExecutorSupervisor,new_execution_owner
from huginn.pipeline_control.persistence.database.unit_of_work import PostgresPipelineUnitOfWork
factory=ManagementConnectionFactory(sys.argv[1],statement_timeout_ms=2000)
service=RunQueuedInvocationService(lambda:PostgresPipelineUnitOfWork(factory),lambda:PostgresExecutionGuard(factory),ProcessExecutorSupervisor(command=(sys.executable,sys.argv[2],sys.argv[3]),heartbeat_seconds=0.1),new_execution_owner)
service.execute(RunQueuedInvocationRequest('crash-fixture'))
""")
    # Ensure the pytest owner adopts and can reap the deliberately orphaned child.
    ProcessExecutorSupervisor()
    parent = subprocess.Popen(
        [
            sys.executable,
            str(parent_script),
            integration_database_url,
            str(child_script),
            str(marker),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    child_pid = None
    factory = ManagementConnectionFactory(integration_database_url)
    try:
        deadline = time.monotonic() + 10
        while (
            not marker.exists()
            and parent.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        assert marker.exists()
        child_pid = int(marker.read_text())
        parent.kill()
        parent.wait(timeout=3)
        blocked = PostgresExecutionGuard(factory)
        assert blocked.acquire(new_execution_owner(None)) is False
        blocked.close()
        recovery = PostgresExecutionGuard(factory)
        owner, identity = recovery.inspect_invocation(invocation_id)
        assert identity.pid == child_pid
        assert ProcessExecutorSupervisor().prove_stopped(owner, identity) is False
        from huginn.pipeline_control.application.errors.execution import (
            ExecutionUnavailableError,
        )

        with pytest.raises(ExecutionUnavailableError, match="executor_stop_unproven"):
            ReconcileInvocationService(recovery, ProcessExecutorSupervisor()).execute(
                ReconcileInvocationRequest(invocation_id, True)
            )
        os.killpg(child_pid, signal.SIGTERM)
        deadline = time.monotonic() + 3
        while group_members(child_pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert group_members(child_pid) == ()
        with suppress(ChildProcessError):
            os.waitpid(child_pid, 0)
        assert (
            ReconcileInvocationService(recovery, ProcessExecutorSupervisor())
            .execute(ReconcileInvocationRequest(invocation_id, True))
            .status
            == "interrupted"
        )
        with psycopg.connect(integration_database_url) as connection:
            assert connection.execute(
                "SELECT active FROM ops.pipeline_execution_guard"
            ).fetchone() == (False,)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)
        if child_pid is not None:
            with suppress(ProcessLookupError):
                os.killpg(child_pid, signal.SIGKILL)
            with suppress(ChildProcessError):
                os.waitpid(child_pid, 0)
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "UPDATE ops.pipeline_execution_guard SET active=FALSE WHERE invocation_id=%s",
                (invocation_id,),
            )
        _delete_invocation(integration_database_url, account_id, invocation_id)


def test_supported_full_cli_busy_and_queued_worker_wait_until_standalone_guard_releases(
    integration_database_url, monkeypatch
):
    from huginn.config import Config
    from huginn.elt import __main__ as full_cli
    from huginn.pipeline_control.application.requests.run_queued_invocation_request import (
        RunQueuedInvocationRequest,
    )
    from huginn.pipeline_control.application.services.run_queued_invocation_service import (
        RunQueuedInvocationService,
    )

    factory = ManagementConnectionFactory(integration_database_url)
    account_id, invocation_id = _create_invocation(integration_database_url)
    standalone_owner = new_execution_owner(None)
    standalone = PostgresExecutionGuard(factory)
    script = "import json,sys; from dataclasses import asdict; from huginn.pipeline_control.infrastructure.process_supervisor import current_identity; print(json.dumps(asdict(current_identity())),flush=True); assert sys.stdin.readline()=='GO\\n'"
    supervisor = ProcessExecutorSupervisor(
        command=(sys.executable, "-c", script), heartbeat_seconds=0.05
    )
    service = RunQueuedInvocationService(
        lambda: PostgresPipelineUnitOfWork(factory),
        lambda: PostgresExecutionGuard(factory),
        supervisor,
        new_execution_owner,
    )
    try:
        assert standalone.acquire(standalone_owner)
        monkeypatch.setattr(
            full_cli,
            "load_config",
            lambda: Config(
                database_url=integration_database_url,
                yc_algolia_api_key="harmless-fixture",
            ),
        )
        with pytest.raises(SystemExit) as busy:
            full_cli.main()
        assert busy.value.code == 1
        assert (
            service.execute(RunQueuedInvocationRequest("waiting-worker")).status
            == "waiting"
        )
        with psycopg.connect(integration_database_url) as connection:
            assert connection.execute(
                "SELECT state,started_at,worker_id FROM ops.pipeline_invocations WHERE id=%s",
                (invocation_id,),
            ).fetchone() == ("queued", None, None)
            assert connection.execute(
                "SELECT count(*) FROM ops.job_runs WHERE invocation_id=%s",
                (invocation_id,),
            ).fetchone() == (0,)
        assert standalone.settle(standalone_owner, "succeeded")
        assert (
            service.execute(RunQueuedInvocationRequest("released-worker")).status
            == "succeeded"
        )
    finally:
        standalone.close()
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "UPDATE ops.pipeline_execution_guard SET active=FALSE WHERE owner_id=%s",
                (standalone_owner.owner_id,),
            )
        _delete_invocation(integration_database_url, account_id, invocation_id)


def test_manual_review_queue_failure_preserves_independent_gold_dependencies(
    integration_database_url,
):
    account_id, invocation_id = _create_invocation(
        integration_database_url, state="running"
    )
    try:
        statuses = run_stages(
            _fixture_stages(
                integration_database_url,
                invocation_id,
                fail_source="silver.manual_review",
            ),
            PostgresJobRunWriter(integration_database_url),
            invocation_id=invocation_id,
            strict_tracking=True,
        )
        assert statuses["silver.manual_review"] == "failed"
        assert statuses["silver.signal_resolution"] == "succeeded"
        assert statuses["gold.company"] == "succeeded"
        assert statuses["gold.company_signal"] == "succeeded"
    finally:
        _delete_invocation(integration_database_url, account_id, invocation_id)

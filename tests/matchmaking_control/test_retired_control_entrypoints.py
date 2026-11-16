"""Control entry points fail closed without constructing persistence adapters."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from huginn.management.application.errors.errors import AuthorizationError
from huginn.management.domain.entities.session import Session
from huginn.management.domain.value_objects.account_role import AccountRole
from huginn.management.domain.value_objects.common import Page, Principal
from huginn.management.presentation.api.dependencies.authentication import (
    AuthenticatedSession,
    get_authenticated_session,
)
from huginn.management.security.tokens import digest_token
from huginn.matchmaking.application.errors.retired import MatchmakingRetiredError
from huginn.matchmaking_control.application.read_models.run_summary import RunSummary
from huginn.matchmaking_control.domain.value_objects.run_state import RunState
from huginn.matchmaking_control.persistence.contracts.repositories.run import (
    RunRepository,
)
from huginn.matchmaking_control.persistence.repositories.run_repository import (
    PostgresRunRepository,
)
from huginn.matchmaking_control.presentation.api.routers.runs import router
from huginn.matchmaking_control.presentation.cli import executor, worker


def test_worker_never_constructs_uow_guard_or_child():
    def unexpected(*_args, **_kwargs):
        pytest.fail("retired worker must not construct runtime adapters")

    with pytest.raises(MatchmakingRetiredError):
        worker.run_once(unexpected, unexpected, unexpected)

    with pytest.raises(SystemExit) as error:
        worker.main(["--once"])
    assert error.value.code == 2


def test_repository_keeps_guard_settlement_but_has_no_admission_or_claim_writer():
    for method in (
        "admit_run",
        "claim_next_run",
        "start_run",
        "start_target",
        "acknowledge_target",
        "pending_targets",
        "heartbeat",
    ):
        assert not hasattr(PostgresRunRepository, method)
        assert not hasattr(RunRepository, method)
    for method in ("finish_run", "reconcile_run", "get_run_snapshot"):
        assert hasattr(PostgresRunRepository, method)
        assert hasattr(RunRepository, method)


def test_supervised_child_exits_retired_after_protocol_ack(monkeypatch, capsys):
    @dataclass
    class Identity:
        owner_id: str
        run_id: None

    monkeypatch.setattr(
        executor,
        "current_identity",
        lambda: Identity("worker", None),
    )
    monkeypatch.setattr("sys.stdin.readline", lambda: "GO\n")

    with pytest.raises(SystemExit) as error:
        executor.main(
            [
                "--run-id",
                "11111111-1111-4111-8111-111111111111",
                "--worker-id",
                "22222222-2222-4222-8222-222222222222",
            ]
        )
    assert error.value.code == 3
    assert json.loads(capsys.readouterr().out)["owner_id"] == "worker"


def test_actual_worker_and_child_modules_fail_closed_without_database():
    root = Path(__file__).parents[2]
    worker_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "huginn.matchmaking_control.presentation.cli.worker",
            "--once",
        ],
        cwd=root,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert worker_result.returncode == 2
    assert "matchmaking_retired" in worker_result.stderr

    child_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "huginn.matchmaking_control.presentation.cli.executor",
            "--run-id",
            "11111111-1111-4111-8111-111111111111",
            "--worker-id",
            "22222222-2222-4222-8222-222222222222",
        ],
        cwd=root,
        env=os.environ.copy(),
        input="GO\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert child_result.returncode == 3
    assert "matchmaking_retired" in child_result.stderr


def test_history_get_remains_available_in_read_only_composition():
    app = FastAPI()
    app.include_router(router)
    now = datetime.now(UTC)
    entry = RunSummary(uuid4(), uuid4(), RunState("interrupted"), now, now, now, 1, 1)
    history = SimpleNamespace(
        execute=lambda _request: SimpleNamespace(page=Page((entry,), 0, 50, False))
    )
    app.state.management = SimpleNamespace(
        matchmaking_services=SimpleNamespace(history=history)
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        Principal(uuid4(), uuid4(), AccountRole("admin")),
        Session(
            uuid4(),
            uuid4(),
            "token-digest",
            digest_token("csrf"),
            now,
            now + timedelta(hours=1),
            None,
        ),
        "session-token",
    )

    response = TestClient(app).get("/api/v1/admin/matchmaking/runs")
    assert response.status_code == 200
    assert response.json()["items"][0]["state"] == "interrupted"
    assert response.json()["items"][0]["id"] == str(entry.id)


def test_admin_trigger_preserves_auth_csrf_and_returns_private_retired_response():
    app = FastAPI()
    app.include_router(router)

    @app.exception_handler(AuthorizationError)
    async def auth_error(_request: Request, _exc: AuthorizationError):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    now = datetime.now(UTC)
    csrf = "test-csrf"
    admin = AuthenticatedSession(
        Principal(uuid4(), uuid4(), AccountRole("admin")),
        Session(
            uuid4(),
            uuid4(),
            "token-digest",
            digest_token(csrf),
            now,
            now + timedelta(hours=1),
            None,
        ),
        "session-token",
    )
    app.dependency_overrides[get_authenticated_session] = lambda: admin
    client = TestClient(app)
    body = {
        "request_id": str(uuid4()),
        "target": {"kind": "all_eligible"},
        "cutoff": now.isoformat(),
        "as_of": now.isoformat(),
    }

    missing_csrf = client.post("/api/v1/admin/matchmaking/runs", json=body)
    assert missing_csrf.status_code == 403

    retired = client.post(
        "/api/v1/admin/matchmaking/runs",
        json=body,
        headers={"X-CSRF-Token": csrf},
    )
    assert retired.status_code == 410
    assert retired.headers["cache-control"] == "no-store"
    assert retired.headers["vary"] == "Cookie"
    assert retired.json()["error"]["code"] == "matchmaking_retired"

    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        Principal(uuid4(), uuid4(), AccountRole("user")),
        admin.session,
        "session-token",
    )
    forbidden = client.post(
        "/api/v1/admin/matchmaking/runs",
        json=body,
        headers={"X-CSRF-Token": csrf},
    )
    assert forbidden.status_code == 403

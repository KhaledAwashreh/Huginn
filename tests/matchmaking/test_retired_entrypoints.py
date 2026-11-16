"""Retired Match creation entry points fail before configuration or storage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from huginn.matchmaking import bootstrap
from huginn.matchmaking.application.errors.retired import MatchmakingRetiredError
from huginn.matchmaking.config import MatchmakingConfig
from huginn.matchmaking.presentation import cli


def test_matchmaking_bootstraps_fail_closed_without_touching_database():
    with pytest.raises(MatchmakingRetiredError) as error:
        bootstrap.build_service(None)  # type: ignore[arg-type]
    assert error.value.code == "matchmaking_retired"

    with pytest.raises(MatchmakingRetiredError):
        bootstrap.build_batch_service(None)  # type: ignore[arg-type]


def test_direct_cli_reports_retired_before_loading_environment(monkeypatch, capsys):
    def unexpected_config():
        pytest.fail("retired CLI must not load runtime configuration")

    monkeypatch.setattr(MatchmakingConfig, "from_env", unexpected_config)
    status = cli.main(
        [
            "--user-id",
            "11111111-1111-4111-8111-111111111111",
            "--cutoff",
            "2026-10-01T00:00:00Z",
        ]
    )

    assert status == 2
    assert json.loads(capsys.readouterr().out) == {
        "error": {
            "code": "matchmaking_retired",
            "message": "Match creation has been retired",
        }
    }


def test_actual_module_cli_fails_closed_without_arguments_or_database():
    root = Path(__file__).parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "huginn.matchmaking"],
        cwd=root,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "matchmaking_retired"

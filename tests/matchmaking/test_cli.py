import json
from datetime import UTC, datetime
from uuid import UUID

from huginn.matchmaking.application.errors.execution import ConfigurationError
from huginn.matchmaking.application.responses.batch_matchmaking_response import (
    BatchMatchmakingResponse,
)
from huginn.matchmaking.application.responses.matchmaking_response import (
    MatchmakingResponse,
    MatchmakingStatus,
)
from huginn.matchmaking.application.responses.user_failure import (
    UserFailure,
    UserFailureReason,
)
from huginn.matchmaking.config import MatchmakingConfig
from huginn.matchmaking.domain.entities.match import Match, MatchStatus
from huginn.matchmaking.presentation import cli


def _response() -> BatchMatchmakingResponse:
    user_id = UUID("11111111-1111-4111-8111-111111111111")
    return BatchMatchmakingResponse(
        cutoff=datetime(2026, 9, 1, tzinfo=UTC),
        as_of=datetime(2026, 10, 1, tzinfo=UTC),
        responses=(
            MatchmakingResponse(
                user_id=user_id,
                status=MatchmakingStatus.SUCCEEDED,
                cutoff=datetime(2026, 9, 1, tzinfo=UTC),
                as_of=datetime(2026, 10, 1, tzinfo=UTC),
                strategies_evaluated=0,
                strategies_skipped=0,
                unique_candidates_count=1,
                created_matches=(
                    Match(
                        id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                        user_id=user_id,
                        company_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
                        status=MatchStatus.NEW,
                        notes=None,
                        created_at=datetime(2026, 10, 1, tzinfo=UTC),
                        updated_at=datetime(2026, 10, 1, tzinfo=UTC),
                    ),
                ),
                existing_matches_skipped_count=0,
                skipped_strategies=(),
            ),
        ),
        failures=(),
    )


def test_invalid_input_emits_safe_json_before_configuration(monkeypatch, capsys):
    def should_not_load_config():
        raise AssertionError("configuration must follow argument validation")

    monkeypatch.setattr(MatchmakingConfig, "from_env", should_not_load_config)

    exit_code = cli.main(
        [
            "--user-id",
            "not-a-uuid",
            "--cutoff",
            "2026-09-01T00:00:00Z",
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().out) == {
        "error": {"code": "invalid_input", "message": "Invalid command-line input"}
    }


def test_invalid_timestamp_is_rejected_before_configuration(monkeypatch, capsys):
    def should_not_load_config():
        raise AssertionError("configuration must follow timestamp validation")

    monkeypatch.setattr(MatchmakingConfig, "from_env", should_not_load_config)

    exit_code = cli.main(
        [
            "--user-id",
            "11111111-1111-4111-8111-111111111111",
            "--cutoff",
            "2026-09-01T00:00:00",
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"


def test_configuration_error_is_safe_json(monkeypatch, capsys):
    def invalid_config():
        raise ConfigurationError("password=do-not-print")

    monkeypatch.setattr(MatchmakingConfig, "from_env", invalid_config)

    exit_code = cli.main(
        [
            "--user-id",
            "11111111-1111-4111-8111-111111111111",
            "--cutoff",
            "2026-09-01T00:00:00Z",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert json.loads(output) == {
        "error": {
            "code": "invalid_configuration",
            "message": "Invalid matchmaking configuration",
        }
    }
    assert "do-not-print" not in output


def test_batch_cli_serializes_contract_and_returns_success(monkeypatch, capsys):
    from huginn.matchmaking import bootstrap

    config = MatchmakingConfig("dbname=huginn")
    response = _response()

    class Service:
        def execute(self, request):
            assert request.user_ids == (
                UUID("11111111-1111-4111-8111-111111111111"),
                UUID("22222222-2222-4222-8222-222222222222"),
            )
            assert request.cutoff == datetime(2026, 9, 1, tzinfo=UTC)
            assert request.as_of == datetime(2026, 10, 1, tzinfo=UTC)
            return response

    monkeypatch.setattr(MatchmakingConfig, "from_env", lambda: config)
    monkeypatch.setattr(bootstrap, "build_batch_service", lambda actual: Service())
    from huginn.matchmaking.presentation.serializers.batch_matchmaking_response import (
        serialize_batch_matchmaking_response,
    )

    monkeypatch.setattr(
        cli,
        "_execute_guarded",
        lambda actual, request: (
            serialize_batch_matchmaking_response(Service().execute(request)),
            1 if response.failures else 0,
        ),
    )

    exit_code = cli.main(
        [
            "--user-id",
            "11111111-1111-4111-8111-111111111111",
            "--user-id",
            "22222222-2222-4222-8222-222222222222",
            "--cutoff",
            "2026-09-01T00:00:00Z",
            "--as-of",
            "2026-10-01T00:00:00+00:00",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"cutoff", "as_of", "responses", "failures"}
    assert payload["cutoff"] == "2026-09-01T00:00:00Z"
    assert payload["as_of"] == "2026-10-01T00:00:00Z"
    assert payload["responses"][0]["status"] == "succeeded"
    assert payload["responses"][0]["created_matches"] == [
        {
            "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "user_id": "11111111-1111-4111-8111-111111111111",
            "company_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "status": "new",
            "notes": None,
            "created_at": "2026-10-01T00:00:00Z",
            "updated_at": "2026-10-01T00:00:00Z",
        }
    ]
    assert payload["failures"] == []


def test_help_keeps_argparse_text(capsys):
    try:
        cli.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("argparse help should exit normally")

    output = capsys.readouterr().out
    assert "usage:" in output
    assert "--user-id" in output


def test_batch_database_failure_returns_exit_one(monkeypatch, capsys):
    from huginn.matchmaking import bootstrap

    user_id = UUID("11111111-1111-4111-8111-111111111111")
    response = BatchMatchmakingResponse(
        cutoff=datetime(2026, 9, 1, tzinfo=UTC),
        as_of=datetime(2026, 10, 1, tzinfo=UTC),
        responses=(),
        failures=(UserFailure(user_id, UserFailureReason.DATABASE_UNAVAILABLE),),
    )

    class Service:
        def execute(self, request):
            return response

    monkeypatch.setattr(
        MatchmakingConfig, "from_env", lambda: MatchmakingConfig("dbname=huginn")
    )
    monkeypatch.setattr(bootstrap, "build_batch_service", lambda actual: Service())
    from huginn.matchmaking.presentation.serializers.batch_matchmaking_response import (
        serialize_batch_matchmaking_response,
    )

    monkeypatch.setattr(
        cli,
        "_execute_guarded",
        lambda actual, request: (
            serialize_batch_matchmaking_response(Service().execute(request)),
            1 if response.failures else 0,
        ),
    )

    exit_code = cli.main(
        [
            "--user-id",
            str(user_id),
            "--cutoff",
            "2026-09-01T00:00:00Z",
        ]
    )

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out)["failures"] == [
        {"user_id": str(user_id), "reason": "database_unavailable"}
    ]

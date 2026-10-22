from __future__ import annotations

import pytest

from huginn.elt.silver.context.__main__ import build_parser, main


def test_parser_requires_command_and_source():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["audit"])


def test_parser_rejects_nonpositive_limit():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["audit", "--source", "yc", "--limit", "0"])


def test_cli_has_no_database_url_argument_and_details_default_is_ignored_path():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["audit", "--source", "yc", "--dsn", "postgres://secret"])

    args = parser.parse_args(["audit", "--source", "yc", "--details"])
    assert str(args.details) == ".local-runtime/source-context/audit-details.json"


def test_invalid_selection_does_not_construct_repository(capsys):
    def should_not_run():
        raise AssertionError("database access started before argument validation")

    with pytest.raises(SystemExit):
        main(
            ["capture", "--source", "yc", "--limit", "-1"],
            repository_factory=should_not_run,
        )


def test_audit_cli_prints_safe_summary_without_source_text(capsys):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    source_text = "Reach me at private.person@example.test"
    source_input = SimpleNamespace(
        source="yc",
        stable_id="1",
        payload={
            "id": 1,
            "slug": "safe-company",
            "name": "Safe Company",
            "one_liner": source_text,
        },
        fetched_at=datetime(2024, 1, 1, tzinfo=UTC),
        last_checked_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    repository = SimpleNamespace(
        read_audit_snapshot=lambda source, limit: SimpleNamespace(
            inputs=(source_input,),
            available_count=1,
            coverage_counts={
                "bronze": 1,
                "silver_staging": 0,
                "silver_resolved": 0,
                "silver_unresolved": 0,
                "gold_signals": 0,
            },
            downstream_by_stable_id={"1": {}},
        )
    )

    result = main(
        ["audit", "--source", "yc"],
        repository_factory=lambda: repository,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert '"input_count": 1' in output
    assert '"one_liner"' in output
    assert source_text not in output


def test_capture_cli_persists_only_after_explicit_capture_command(capsys):
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import UUID

    source_input = SimpleNamespace(
        source="yc",
        stable_id="1",
        payload={"id": 1, "slug": "safe-company", "one_liner": "Short pitch"},
        fetched_at=datetime(2024, 1, 1, tzinfo=UTC),
        last_checked_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    repository = SimpleNamespace(
        read_inputs=lambda source, limit=None, *, read_only=True: [source_input],
        count_inputs=lambda source: 1,
        coverage_counts=lambda source: {
            "bronze": 1,
            "silver_staging": 0,
            "silver_resolved": 0,
            "silver_unresolved": 0,
            "gold_signals": 0,
        },
        persist_run=lambda run: SimpleNamespace(
            run_id=UUID("00000000-0000-0000-0000-000000000001"),
            input_count=1,
            captured_count=1,
            excluded_count=0,
            failed_count=0,
            status="complete",
        ),
    )

    result = main(
        ["capture", "--source", "yc"],
        repository_factory=lambda: repository,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert '"mode": "capture"' in output
    assert '"status": "complete"' in output

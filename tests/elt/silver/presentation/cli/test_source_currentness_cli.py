from __future__ import annotations

import json

from huginn.elt.silver.models.reconcile_result import ReconcileResult
from huginn.elt.silver.presentation.cli import source_currentness as cli


class FakeRepository:
    def __init__(self):
        self.calls = []

    def read_inputs(self, source, limit=None):
        self.calls.append(("read", source, limit))
        return ()

    def reconcile(self, item, facts):
        self.calls.append(("reconcile", item.stable_id))
        return ReconcileResult("unchanged", None)


def test_cli_audit_accepts_all_sources_and_emits_aggregate_json(monkeypatch, capsys):
    repo = FakeRepository()
    monkeypatch.setattr(cli, "_default_repository", lambda: repo)

    code = cli.main(["audit", "--source", "hn"])

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["source"] == "hn"
    assert report["selected_count"] == 0
    assert repo.calls == [("read", "hn", None)]


def test_cli_returns_nonzero_for_stale_reconcile_and_writes_summary(
    monkeypatch, tmp_path
):
    repo = FakeRepository()
    summary = tmp_path / "summary.json"

    def reconcile(source, repository, **kwargs):
        report = {
            "mode": "reconcile",
            "source": source,
            "status": "partial",
            "reconcile_counts": {"created": 0, "unchanged": 0, "stale": 1},
            "invalid_or_unknown_count": 0,
        }
        kwargs["summary_path"].write_text(json.dumps(report))
        return report

    monkeypatch.setattr(cli, "_default_repository", lambda: repo)
    monkeypatch.setattr(cli, "run_reconcile", reconcile)

    code = cli.main(["reconcile", "--source", "yc", "--summary", str(summary)])

    assert code == 1
    assert json.loads(summary.read_text())["status"] == "partial"


def test_cli_returns_interrupt_exit_code_for_interrupted_report(monkeypatch):
    repo = FakeRepository()
    monkeypatch.setattr(cli, "_default_repository", lambda: repo)
    monkeypatch.setattr(
        cli,
        "run_reconcile",
        lambda *args, **kwargs: {
            "status": "partial",
            "error_type": "KeyboardInterrupt",
        },
    )

    assert cli.main(["reconcile", "--source", "yc"]) == 130


def test_cli_invalid_limit_rejected_by_argparse():
    try:
        cli.build_parser().parse_args(["audit", "--source", "yc", "--limit", "0"])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("nonpositive limit should be rejected")

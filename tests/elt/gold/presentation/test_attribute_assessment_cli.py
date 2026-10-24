"""CLI validates explicit windows and keeps lineage output private."""

import json
import stat

from huginn.elt.gold.presentation.cli.attribute_assessment import main
from tests.elt.gold.services.test_attribute_assessment_service import Repository


def test_cli_writes_aggregate_and_restricted_receipts(tmp_path, capsys):
    summary = tmp_path / "report.json"
    receipts = tmp_path / "receipts.json"
    assert (
        main(
            [
                "--cutoff",
                "2026-09-01T00:00:00+00:00",
                "--as-of",
                "2026-10-01T00:00:00+00:00",
                "--summary",
                str(summary),
                "--receipts",
                str(receipts),
            ],
            repository_factory=Repository,
        )
        == 0
    )
    assert json.loads(summary.read_text())["status"] == "complete"
    assert len(json.loads(receipts.read_text())) == 3
    assert stat.S_IMODE(receipts.stat().st_mode) == 0o600
    assert "raw-token" not in capsys.readouterr().out


def test_failure_does_not_expose_connection_credentials(capsys):
    def failure():
        raise RuntimeError("postgres://secret:password@private-host/db")

    assert (
        main(
            ["--cutoff", "2026-09-01T00:00:00Z", "--as-of", "2026-10-01T00:00:00Z"],
            repository_factory=failure,
        )
        == 1
    )
    output = capsys.readouterr()
    assert "secret" not in output.err
    assert "RuntimeError" in output.err


def test_output_paths_cannot_overwrite_each_other(tmp_path, capsys):
    target = tmp_path / "report.json"
    assert (
        main(
            [
                "--cutoff",
                "2026-09-01T00:00:00Z",
                "--as-of",
                "2026-10-01T00:00:00Z",
                "--summary",
                str(target),
                "--receipts",
                str(target),
            ],
            repository_factory=Repository,
        )
        == 1
    )
    assert not target.exists()

import os

import pytest

from huginn.matchmaking.presentation.write_ranking_output import write_ranking_output


def test_write_failure_leaves_no_partial_snapshot_and_can_retry(tmp_path, monkeypatch):
    target = tmp_path / "snapshot.json"
    original = os.fsync

    def fail(_):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        write_ranking_output(target, "complete")
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setattr(os, "fsync", original)
    write_ranking_output(target, "complete")
    assert target.read_text() == "complete"
    with pytest.raises(FileExistsError):
        write_ranking_output(target, "replacement")
    assert target.read_text() == "complete"

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.matchmaking.domain.entities.match import Match, MatchStatus
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow


def test_match_is_immutable_and_has_the_workflow_status_values():
    now = datetime(2026, 10, 7, tzinfo=UTC)
    match = Match(uuid4(), uuid4(), uuid4(), MatchStatus.NEW, None, now, now)

    assert match.status is MatchStatus.NEW
    assert [status.value for status in MatchStatus] == [
        "new",
        "contacted",
        "responded",
        "dismissed",
        "converted",
    ]
    with pytest.raises(FrozenInstanceError):
        match.notes = "changed"


def test_signal_window_normalizes_offsets_and_accepts_equal_bounds():
    cutoff = datetime.fromisoformat("2026-10-07T10:00:00+02:00")
    window = SignalWindow(cutoff, cutoff)

    assert window.cutoff == datetime(2026, 10, 7, 8, tzinfo=UTC)
    assert window.as_of == window.cutoff


@pytest.mark.parametrize(
    "cutoff,as_of",
    [
        (datetime(2026, 10, 7), datetime(2026, 10, 8, tzinfo=UTC)),
        (datetime(2026, 10, 7, tzinfo=UTC), datetime(2026, 10, 8)),
        (
            datetime(2026, 10, 8, tzinfo=UTC),
            datetime(2026, 10, 7, tzinfo=UTC),
        ),
    ],
)
def test_signal_window_rejects_naive_or_reversed_values(cutoff, as_of):
    with pytest.raises(ValueError):
        SignalWindow(cutoff, as_of)

from datetime import UTC, datetime

import pytest

from huginn.management.domain.policies.discovery_resolution import (
    decide_discovery,
    reverse_rejection,
)
from huginn.management.domain.policies.later_pause import capture_later_pause
from huginn.management.domain.value_objects.discovery_resolution import (
    DiscoveryResolution,
)
from huginn.management.domain.value_objects.pause_choice import PauseChoice


def test_save_converts_discovery_without_closing_or_mutating_pursuit():
    decision = decide_discovery(DiscoveryResolution("save"))
    assert decision.status.value == "converted"
    assert decision.create_prospect is True
    assert decision.add_rejection is False
    assert decision.add_pause is False
    assert decision.prospect_initial_stage == "saved"


def test_not_relevant_rejects_and_later_only_adds_a_pause():
    rejected = decide_discovery(DiscoveryResolution("not_relevant"))
    assert rejected.status.value == "rejected"
    assert rejected.add_rejection is True
    assert rejected.create_prospect is False
    now = datetime(2027, 1, 1, tzinfo=UTC)
    pause = capture_later_pause(
        PauseChoice("indefinite"),
        repeat_interval_days=30,
        preference_updated_at=now,
        expected_repeat_interval_days=30,
        expected_preference_updated_at=now,
        selected_at=now,
    )
    later = decide_discovery(DiscoveryResolution("later"), pause=pause)
    assert later.status.value == "open"
    assert later.add_pause is True
    assert later.pause == pause
    untouched = decide_discovery(DiscoveryResolution("none"))
    assert untouched.status.value == "open"
    assert not untouched.add_pause and not untouched.add_rejection


def test_later_can_capture_finite_pause_without_changing_resolution():
    until = datetime(2027, 1, 1, tzinfo=UTC)
    pause = capture_later_pause(
        PauseChoice("x1"),
        repeat_interval_days=1,
        preference_updated_at=until,
        expected_repeat_interval_days=1,
        expected_preference_updated_at=until,
        selected_at=until,
    )
    decision = decide_discovery(DiscoveryResolution("later"), pause=pause)
    assert decision.status.value == "open"
    assert decision.pause == pause


def test_unknown_action_is_rejected_and_reversal_only_clears_rejection():
    with pytest.raises(ValueError):
        decide_discovery(DiscoveryResolution("close"))
    reversal = reverse_rejection()
    assert reversal.clear_rejection is True
    assert reversal.reopen_recommendation is False
    assert reversal.generate_recommendation is False

from datetime import UTC, datetime, timedelta

import pytest

from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.domain.policies.later_pause import capture_later_pause
from huginn.management.domain.value_objects.pause_choice import PauseChoice


def test_finite_pause_uses_server_preference_snapshot_and_survives_future_changes():
    now = datetime(2027, 1, 1, tzinfo=UTC)
    updated = datetime(2026, 12, 1, tzinfo=UTC)
    pause = capture_later_pause(
        PauseChoice("x2"),
        repeat_interval_days=30,
        preference_updated_at=updated,
        expected_repeat_interval_days=30,
        expected_preference_updated_at=updated,
        selected_at=now,
    )
    assert pause.expires_at == now + timedelta(days=60)
    assert pause.repeat_interval_days == 30
    assert pause.preference_updated_at == updated


def test_indefinite_pause_has_no_expiry_and_stale_duration_choice_conflicts():
    now = datetime(2027, 1, 1, tzinfo=UTC)
    updated = datetime(2026, 12, 1, tzinfo=UTC)
    pause = capture_later_pause(
        PauseChoice("indefinite"),
        repeat_interval_days=30,
        preference_updated_at=updated,
        expected_repeat_interval_days=30,
        expected_preference_updated_at=updated,
        selected_at=now,
    )
    assert pause.expires_at is None
    with pytest.raises(ConflictError):
        capture_later_pause(
            PauseChoice("x2"),
            repeat_interval_days=45,
            preference_updated_at=updated,
            expected_repeat_interval_days=30,
            expected_preference_updated_at=updated,
            selected_at=now,
        )


def test_later_requires_a_server_resolved_pause_snapshot():
    from huginn.management.domain.policies.discovery_resolution import decide_discovery
    from huginn.management.domain.value_objects.discovery_resolution import (
        DiscoveryResolution,
    )

    with pytest.raises(ValidationDomainError):
        decide_discovery(DiscoveryResolution("later"))

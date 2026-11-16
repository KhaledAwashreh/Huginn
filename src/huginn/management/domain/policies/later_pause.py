from datetime import datetime, timedelta

from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.domain.value_objects.later_pause import LaterPause
from huginn.management.domain.value_objects.pause_choice import PauseChoice


def capture_later_pause(
    choice: PauseChoice,
    *,
    repeat_interval_days: int,
    preference_updated_at: datetime,
    expected_repeat_interval_days: int,
    expected_preference_updated_at: datetime,
    selected_at: datetime,
) -> LaterPause:
    if not isinstance(choice, PauseChoice):
        raise ValidationDomainError("Pause choice must use its domain value")
    if (
        repeat_interval_days != expected_repeat_interval_days
        or preference_updated_at != expected_preference_updated_at
    ):
        raise ConflictError("Repeat interval changed; review the Later duration")
    if type(repeat_interval_days) is not int or repeat_interval_days < 1:
        raise ValidationDomainError("Repeat interval must be positive")
    if choice.value == "indefinite":
        expires_at = None
    else:
        expires_at = selected_at + timedelta(
            days=int(choice.value[1:]) * repeat_interval_days
        )
    return LaterPause(
        choice,
        repeat_interval_days,
        preference_updated_at,
        selected_at,
        expires_at,
    )

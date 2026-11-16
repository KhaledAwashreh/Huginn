"""Pure projection of append-only activity-time corrections."""

from datetime import datetime

from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.corrected_activity_occurrence import (
    CorrectedActivityOccurrence,
)


def project_activity_occurrence(
    original: ProspectActivity, history: tuple[ProspectActivity, ...]
) -> CorrectedActivityOccurrence:
    if (
        not isinstance(original, ProspectActivity)
        or original.kind.value == "correction"
    ):
        raise ValidationDomainError(
            "Occurrence corrections must target an original activity"
        )
    if not all(isinstance(activity, ProspectActivity) for activity in history):
        raise ValidationDomainError("Activity history must use its domain values")
    corrections = tuple(
        activity for activity in history if activity.correction_of_id == original.id
    )
    if any(
        activity.kind.value != "correction"
        or (activity.business_id, activity.prospect_id)
        != (original.business_id, original.prospect_id)
        for activity in corrections
    ):
        raise ValidationDomainError("Correction history does not match its original")
    if any(
        type(activity.payload.value.get("correction_sequence")) is not int
        or activity.payload.value["correction_sequence"] < 1
        for activity in corrections
    ):
        raise ValidationDomainError("Correction sequence must be a positive integer")

    current = original.occurred_at
    head_id = None
    for expected_sequence, correction in enumerate(
        sorted(
            corrections,
            key=lambda activity: activity.payload.value["correction_sequence"],
        ),
        start=1,
    ):
        payload = correction.payload.value
        if payload.get("correction_sequence") != expected_sequence:
            raise ValidationDomainError("Correction sequence must be contiguous")
        prior = _parse_timestamp(payload.get("prior"))
        replacement = _parse_timestamp(payload.get("replacement"))
        if prior != current:
            raise ValidationDomainError(
                "Correction prior time does not match its history"
            )
        current = replacement
        head_id = correction.id
    return CorrectedActivityOccurrence(
        original.id,
        current,
        head_id,
        len(corrections),
    )


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValidationDomainError("Correction timestamps must be ISO strings")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationDomainError("Correction timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationDomainError("Correction timestamp must include a timezone")
    return parsed

"""Explicit discovery-to-pursuit decisions, design.md decision 2."""

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.discovery_decision import (
    DiscoveryDecision,
)
from huginn.management.domain.value_objects.discovery_resolution import (
    DiscoveryResolution,
)
from huginn.management.domain.value_objects.later_pause import LaterPause
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.domain.value_objects.rejection_reversal import RejectionReversal


def decide_discovery(
    action: DiscoveryResolution, *, pause: LaterPause | None = None
) -> DiscoveryDecision:
    if not isinstance(action, DiscoveryResolution):
        raise ValidationDomainError("Discovery action must use the domain vocabulary")
    if action.value == "save":
        if pause is not None:
            raise ValidationDomainError("Save cannot also create a pause")
        return DiscoveryDecision(
            RecommendationStatus("converted"), True, "saved", False, False, None
        )
    if action.value == "not_relevant":
        if pause is not None:
            raise ValidationDomainError("Not relevant cannot also create a pause")
        return DiscoveryDecision(
            RecommendationStatus("rejected"), False, None, True, False, None
        )
    if action.value == "later":
        if not isinstance(pause, LaterPause):
            raise ValidationDomainError(
                "Later requires the server-resolved duration snapshot"
            )
        return DiscoveryDecision(
            RecommendationStatus("open"), False, None, False, True, pause
        )
    if action.value == "none":
        if pause is not None:
            raise ValidationDomainError("No action cannot create a pause")
        return DiscoveryDecision(
            RecommendationStatus("open"), False, None, False, False, None
        )
    raise ValidationDomainError("Unsupported discovery action")


def reverse_rejection() -> RejectionReversal:
    return RejectionReversal()

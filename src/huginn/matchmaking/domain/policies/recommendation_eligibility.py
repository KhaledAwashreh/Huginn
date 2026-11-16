"""Pure current-state gates for any recommendation channel, design.md decisions 1-2."""

from datetime import datetime

from huginn.matchmaking.domain.value_objects._ranking_validation import aware
from huginn.matchmaking.domain.value_objects.business_company_state import (
    BusinessCompanyState,
)
from huginn.matchmaking.domain.value_objects.recommendation_eligibility import (
    RecommendationEligibility,
)


def assess_recommendation_eligibility(
    state: BusinessCompanyState, at: datetime
) -> RecommendationEligibility:
    aware(at, "at")
    blockers = []
    if state.paused_indefinitely or (
        state.paused_until is not None and at < state.paused_until
    ):
        blockers.append("paused")
    if state.cooldown_until is not None and at < state.cooldown_until:
        blockers.append("cooldown")
    if state.rejected:
        blockers.append("rejected")
    if state.has_relationship:
        blockers.append("relationship")
    if state.uncertain_delivery:
        blockers.append("uncertain_delivery")
    if state.pending_delivery:
        blockers.append("pending_delivery")
    return RecommendationEligibility(not blockers, tuple(blockers))

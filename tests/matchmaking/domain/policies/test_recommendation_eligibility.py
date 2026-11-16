from datetime import UTC, datetime, timedelta

from huginn.matchmaking.domain.policies.recommendation_eligibility import (
    assess_recommendation_eligibility,
)
from huginn.matchmaking.domain.value_objects.business_company_state import (
    BusinessCompanyState,
)

NOW = datetime(2027, 1, 1, tzinfo=UTC)


def test_never_presented_company_has_no_implicit_cooldown():
    state = BusinessCompanyState()
    result = assess_recommendation_eligibility(state, NOW)
    assert result.eligible is True
    assert result.blockers == ()


def test_exact_expiry_boundary_is_eligible_and_earlier_time_is_not():
    state = BusinessCompanyState(cooldown_until=NOW)
    assert not assess_recommendation_eligibility(
        state, NOW - timedelta(microseconds=1)
    ).eligible
    assert assess_recommendation_eligibility(state, NOW).eligible


def test_blocks_are_independent_and_relationship_includes_closed_prospects():
    state = BusinessCompanyState(
        paused_indefinitely=True,
        rejected=True,
        has_relationship=True,
        uncertain_delivery=True,
        pending_delivery=True,
    )
    result = assess_recommendation_eligibility(state, NOW)
    assert result.eligible is False
    assert result.blockers == (
        "paused",
        "rejected",
        "relationship",
        "uncertain_delivery",
        "pending_delivery",
    )


def test_expiring_pause_does_not_clear_cooldown_or_other_blocks():
    state = BusinessCompanyState(
        cooldown_until=NOW + timedelta(days=1),
        paused_until=NOW,
        rejected=True,
    )
    result = assess_recommendation_eligibility(state, NOW)
    assert result.blockers == ("cooldown", "rejected")

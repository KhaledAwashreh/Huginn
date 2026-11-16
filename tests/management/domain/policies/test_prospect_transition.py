import pytest

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.policies.prospect_transition import (
    reopen_prospect,
    transition_prospect,
)
from huginn.management.domain.value_objects.prospect_stage import ProspectStage


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("saved", "contacted"),
        ("contacted", "in_conversation"),
        ("in_conversation", "proposal_sent"),
        ("proposal_sent", "won_client"),
        ("contacted", "saved"),
        ("in_conversation", "contacted"),
        ("proposal_sent", "in_conversation"),
    ],
)
def test_adjacent_stage_changes_are_allowed(before, after):
    reason = (
        "Changed plan"
        if before in {"contacted", "in_conversation", "proposal_sent"}
        and after != "won_client"
        else None
    )
    assert (
        transition_prospect(
            ProspectStage(before), ProspectStage(after), reason=reason
        ).value
        == after
    )


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("saved", "proposal_sent"),
        ("saved", "won_client"),
        ("won_client", "proposal_sent"),
        ("closed", "contacted"),
    ],
)
def test_non_adjacent_or_closed_stage_changes_are_rejected(before, after):
    with pytest.raises(ValidationDomainError):
        transition_prospect(ProspectStage(before), ProspectStage(after))


def test_backward_and_close_transitions_require_a_reason():
    with pytest.raises(ValidationDomainError):
        transition_prospect(
            ProspectStage("proposal_sent"), ProspectStage("in_conversation")
        )
    with pytest.raises(ValidationDomainError):
        transition_prospect(ProspectStage("contacted"), ProspectStage("closed"))
    assert (
        transition_prospect(
            ProspectStage("proposal_sent"),
            ProspectStage("in_conversation"),
            reason="Revised scope",
        ).value
        == "in_conversation"
    )
    assert (
        transition_prospect(
            ProspectStage("contacted"), ProspectStage("closed"), reason="No response"
        ).value
        == "closed"
    )


def test_close_is_only_from_active_pursuit_and_reopen_restores_last_active_stage():
    with pytest.raises(ValidationDomainError):
        transition_prospect(
            ProspectStage("won_client"), ProspectStage("closed"), reason="Completed"
        )
    assert (
        reopen_prospect(ProspectStage("closed"), ProspectStage("in_conversation")).value
        == "in_conversation"
    )
    with pytest.raises(ValidationDomainError):
        reopen_prospect(ProspectStage("saved"), ProspectStage("saved"))

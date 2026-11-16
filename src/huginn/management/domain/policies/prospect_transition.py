"""Manual pursuit-stage transitions, docs/architecture.md section 9."""

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.prospect_stage import ProspectStage

_ACTIVE = ("saved", "contacted", "in_conversation", "proposal_sent")
_FORWARD = {
    "saved": "contacted",
    "contacted": "in_conversation",
    "in_conversation": "proposal_sent",
    "proposal_sent": "won_client",
}
_BACKWARD = {
    "contacted": "saved",
    "in_conversation": "contacted",
    "proposal_sent": "in_conversation",
    "won_client": "proposal_sent",
}


def transition_prospect(
    current: ProspectStage, target: ProspectStage, *, reason: str | None = None
) -> ProspectStage:
    if not isinstance(current, ProspectStage) or not isinstance(target, ProspectStage):
        raise ValidationDomainError("Prospect stages must use their domain value")
    before, after = current.value, target.value
    if after == "closed":
        if before not in _ACTIVE:
            raise ValidationDomainError("Only an active prospect can be closed")
        _require_reason(reason, "Closing a prospect requires a reason")
        return target
    if _FORWARD.get(before) == after:
        return target
    if _BACKWARD.get(before) == after:
        _require_reason(reason, "Moving a prospect backward requires a reason")
        return target
    raise ValidationDomainError("Prospect stages must change one adjacent step")


def reopen_prospect(
    current: ProspectStage, last_active_stage: ProspectStage
) -> ProspectStage:
    if (
        not isinstance(current, ProspectStage)
        or not isinstance(last_active_stage, ProspectStage)
        or current.value != "closed"
        or last_active_stage.value not in _ACTIVE
    ):
        raise ValidationDomainError(
            "Only a closed prospect can reopen to its last active stage"
        )
    return last_active_stage


def _require_reason(reason: str | None, message: str) -> None:
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationDomainError(message)

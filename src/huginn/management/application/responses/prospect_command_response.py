"""Committed result for a manual prospect command."""

from dataclasses import dataclass

from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class ProspectCommandResponse:
    prospect: Prospect
    activity: ProspectActivity

    def __post_init__(self) -> None:
        if not isinstance(self.prospect, Prospect) or not isinstance(
            self.activity, ProspectActivity
        ):
            raise ValidationDomainError(
                "Prospect command result needs state and activity"
            )
        if (self.prospect.business_id, self.prospect.id) != (
            self.activity.business_id,
            self.activity.prospect_id,
        ):
            raise ValidationDomainError(
                "Activity does not belong to the returned prospect"
            )

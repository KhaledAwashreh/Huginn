"""Owner-visible hidden company decisions and remaining independent blocks."""

from dataclasses import dataclass
from datetime import datetime

from huginn.management.application.read_models.current_company import CurrentCompany
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.matchmaking.domain.policies.recommendation_eligibility import (
    assess_recommendation_eligibility,
)
from huginn.matchmaking.domain.value_objects.business_company_state import (
    BusinessCompanyState,
)


@dataclass(frozen=True, slots=True)
class ManageableSuppressionView:
    company: CurrentCompany
    active_blocks: tuple[SuppressionBlock, ...]
    prospect: Prospect | None
    selection_state: BusinessCompanyState
    read_at: datetime

    @property
    def selection_blockers(self) -> tuple[str, ...]:
        return assess_recommendation_eligibility(
            self.selection_state, self.read_at
        ).blockers

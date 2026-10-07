from typing import Protocol

from huginn.matchmaking.application.read_models.company_candidate import (
    CompanyCandidate,
)
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow


class CandidateRepository(Protocol):
    def find_candidates(
        self, criteria: CompiledCriteria, window: SignalWindow
    ) -> tuple[CompanyCandidate, ...]: ...

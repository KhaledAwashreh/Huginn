"""Coordinate pure ICP filtering and candidate repository selection."""

from typing import Any

from huginn.management.domain.entities.ideal_client_profile import IdealClientProfile
from huginn.management.domain.services.icp_evaluator import candidate_filter
from huginn.management.persistence.contracts.repositories.candidate import (
    CandidateRepository,
)


def evaluate_icp(
    profile: IdealClientProfile,
    candidates: CandidateRepository,
) -> list[Any]:
    criteria = candidate_filter(profile)
    return [] if criteria is None else candidates.find_candidates(criteria)

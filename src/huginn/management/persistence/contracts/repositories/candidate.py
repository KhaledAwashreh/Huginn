"""Candidate-selection repository contract for ICP evaluation."""

from typing import Any, Protocol

from huginn.management.domain.value_objects.icp_filter import IcpCandidateFilter


class CandidateRepository(Protocol):
    def find_candidates(self, criteria: IcpCandidateFilter) -> list[Any]: ...

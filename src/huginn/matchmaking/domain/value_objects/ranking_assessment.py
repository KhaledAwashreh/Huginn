import math
from dataclasses import dataclass
from uuid import UUID

from huginn.matchmaking.domain.constants.research_ranking import (
    CONTEXT_POINTS,
    EVIDENCE_BASES,
    PREFERENCE_MATCHES,
    SERVICE_POINTS,
)
from huginn.matchmaking.domain.value_objects._ranking_validation import (
    require,
    string_tuple,
    text,
)
from huginn.matchmaking.domain.value_objects.ranking_evidence import RankingEvidence
from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)
from huginn.matchmaking.domain.value_objects.ranking_restriction import (
    RankingRestriction,
)


@dataclass(frozen=True)
class RankingAssessment:
    company_id: UUID
    assessment_id: UUID
    service_fit: str
    business_context: str
    service_basis: str
    context_basis: str
    industry_match: str
    size_match: str
    country_match: str
    observations: tuple[RankingObservation, ...]
    evidence: tuple[RankingEvidence, ...]
    relevant_observation_ids: tuple[UUID, ...]
    timing_observation_id: UUID | None
    unknowns: tuple[str, ...]
    rationale: str
    restrictions: tuple[RankingRestriction, ...] = ()
    semantic_service_logit: float | None = None
    semantic_model_reference: str | None = None

    def __post_init__(self) -> None:
        require(
            (self.semantic_service_logit is None)
            == (self.semantic_model_reference is None),
            "Semantic logit and model reference must be supplied together",
        )
        if self.semantic_service_logit is not None:
            require(
                type(self.semantic_service_logit) in (int, float),
                "Semantic logit must be a finite number",
            )
            try:
                finite = math.isfinite(self.semantic_service_logit)
            except OverflowError:
                finite = False
            require(finite, "Semantic logit must be a finite number")
            text(self.semantic_model_reference, "Semantic model reference")
            require(
                len(self.semantic_model_reference) <= 256,
                "Semantic model reference exceeds 256 characters",
            )
        require(
            isinstance(self.company_id, UUID) and isinstance(self.assessment_id, UUID),
            "Invalid assessment identifier",
        )
        require(
            type(self.service_fit) is str and self.service_fit in SERVICE_POINTS,
            "Invalid service fit",
        )
        require(
            type(self.business_context) is str
            and self.business_context in CONTEXT_POINTS,
            "Invalid business context",
        )
        for name in ("service_basis", "context_basis"):
            require(getattr(self, name) in EVIDENCE_BASES, "Invalid evidence basis")
        for name in ("industry_match", "size_match", "country_match"):
            require(
                getattr(self, name) in PREFERENCE_MATCHES, "Invalid preference match"
            )
        text(self.rationale, "Assessment rationale")
        string_tuple(self.unknowns, "Unknowns")
        for name, cls in (
            ("observations", RankingObservation),
            ("evidence", RankingEvidence),
            ("restrictions", RankingRestriction),
        ):
            values = getattr(self, name)
            require(
                type(values) is tuple and all(isinstance(v, cls) for v in values),
                f"{name} must be an immutable typed tuple",
            )
        require(
            bool(self.observations) and bool(self.evidence),
            "Original observations and evidence required",
        )
        observations = {o.observation_id: o for o in self.observations}
        require(
            len(observations) == len(self.observations),
            "Duplicate observation identifier",
        )
        require(len(set(self.evidence)) == len(self.evidence), "Duplicate evidence")
        require(
            type(self.relevant_observation_ids) is tuple
            and bool(self.relevant_observation_ids),
            "Relevant observations must be an immutable nonempty tuple",
        )
        require(
            all(isinstance(i, UUID) for i in self.relevant_observation_ids),
            "Invalid relevant observation identifier",
        )
        relevant = set(self.relevant_observation_ids)
        require(
            len(relevant) == len(self.relevant_observation_ids)
            and relevant <= observations.keys(),
            "Invalid relevant observation references",
        )
        require(
            self.timing_observation_id is None
            or self.timing_observation_id in relevant,
            "Timing must reference a relevant observation",
        )
        for evidence in self.evidence + tuple(r.evidence for r in self.restrictions):
            require(
                evidence.observation_id in observations, "Unknown evidence observation"
            )
            require(
                evidence.quote in observations[evidence.observation_id].description,
                "Evidence quote is not in its original source",
            )
        require(
            relevant <= {e.observation_id for e in self.evidence},
            "Each relevant observation requires quoted evidence",
        )

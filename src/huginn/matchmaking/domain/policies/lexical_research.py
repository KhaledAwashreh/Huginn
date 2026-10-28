"""Conservative topic retrieval baseline, docs/research-ranking.md."""

import re
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from huginn.matchmaking.domain.value_objects.ranking_assessment import RankingAssessment
from huginn.matchmaking.domain.value_objects.ranking_evidence import RankingEvidence
from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)

_STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "company",
        "companies",
        "consultancy",
        "consulting",
        "consultant",
        "consultants",
        "customer",
        "customers",
        "deliver",
        "delivery",
        "for",
        "from",
        "help",
        "helps",
        "helping",
        "how",
        "in",
        "into",
        "is",
        "it",
        "its",
        "my",
        "of",
        "on",
        "or",
        "our",
        "provide",
        "provides",
        "providing",
        "service",
        "services",
        "solution",
        "solutions",
        "team",
        "teams",
        "that",
        "the",
        "their",
        "them",
        "they",
        "this",
        "to",
        "us",
        "we",
        "with",
        "work",
        "works",
        "working",
        "you",
        "your",
    ]
)


def offering_terms(text: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                term.casefold()
                for term in re.findall(r"\w+", text)
                if len(term) >= 4 and term.casefold() not in _STOP_WORDS
            }
        )
    )[:24]


def _excerpt(text: str, match: re.Match) -> str:
    words = tuple(re.finditer(r"\S+", text))
    index = next(i for i, word in enumerate(words) if word.end() > match.start())
    start = max(0, index - 8)
    end = min(len(words), start + 25)
    return text[words[start].start() : words[end - 1].end()]


def assess_topic_overlap(
    company_id: UUID,
    observations: tuple[RankingObservation, ...],
    terms: tuple[str, ...],
    as_of: datetime,
    *,
    industry_match: str = "unknown",
    size_match: str = "unknown",
    country_match: str = "unknown",
) -> RankingAssessment | None:
    evidence = []
    relevant = []
    hits = set()
    for observation in sorted(observations, key=lambda item: item.observation_id):
        if any(
            date is not None and date > as_of
            for date in (observation.occurred_at, observation.observed_at)
        ):
            continue
        found = [
            (
                term,
                re.search(
                    r"(?<!\w)" + re.escape(term) + r"(?!\w)",
                    observation.description,
                    re.IGNORECASE,
                ),
            )
            for term in terms
        ]
        matches = [(term, match) for term, match in found if match is not None]
        if matches:
            hits.update(term for term, _ in matches)
            relevant.append(observation)
            evidence.append(
                RankingEvidence(
                    observation.observation_id,
                    _excerpt(observation.description, matches[0][1]),
                )
            )
    if not relevant:
        return None
    dated = [
        observation for observation in relevant if observation.occurred_at is not None
    ]
    timing = (
        max(
            dated,
            key=lambda observation: (
                observation.occurred_at,
                observation.observation_id,
            ),
        )
        if dated
        else None
    )
    identity = f"topic-overlap-v1/{company_id}/{as_of.isoformat()}/{','.join(terms)}"
    return RankingAssessment(
        company_id=company_id,
        assessment_id=uuid5(NAMESPACE_URL, identity),
        service_fit="adjacent",
        business_context="unknown",
        service_basis="inferred",
        context_basis="unknown",
        industry_match=industry_match,
        size_match=size_match,
        country_match=country_match,
        observations=observations,
        evidence=tuple(evidence),
        relevant_observation_ids=tuple(
            observation.observation_id for observation in relevant
        ),
        timing_observation_id=None if timing is None else timing.observation_id,
        unknowns=(
            "Topic overlap does not establish an internal problem or buyer need.",
            "Budget, independent-project acceptance, sponsor and delivery constraints are unknown.",
            "The source may describe a service sold to customers rather than the company's own need.",
            "Missing or unmatched company preferences do not exclude research candidates.",
        ),
        rationale="Source text overlaps offering topics: "
        + ", ".join(sorted(hits))
        + ". This supports research but does not establish consulting demand. Business context has not been assessed.",
    )

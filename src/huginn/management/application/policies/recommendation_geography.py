"""Fill missing recommendation country only from explicit, grounded directory facts."""

from dataclasses import replace

from huginn.management.application.policies.country_identity import normalize_country
from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)


def resolve_country_evidence(company: RecommendationCompany) -> RecommendationCompany:
    if normalize_country(company.country):
        return company
    observations = {item.observation_id: item for item in company.observations}
    known = []
    for observation_id, label in company.source_countries:
        observation = observations.get(observation_id)
        country = normalize_country(label)
        if (
            country
            and observation
            and observation.source == "eu_startups"
            and f"category: {label}" in observation.description
        ):
            known.append((country, observation_id))
    if len({country for country, _ in known}) == 1:
        country, observation_id = sorted(known, key=lambda item: str(item[1]))[0]
        return replace(company, country=country, country_evidence_id=observation_id)
    return company

from dataclasses import replace
from uuid import uuid4

from huginn.management.application.policies.recommendation_geography import (
    resolve_country_evidence,
)
from tests.management.test_recommendation_service import Store


def test_explicit_directory_country_is_used_when_gold_country_is_missing():
    company = Store().company
    observation = replace(
        company.observations[0],
        source="eu_startups",
        description="Technical platform work.\ncategory: Greece\nplace: Athens",
    )
    company = replace(
        company,
        observations=(observation,),
        source_countries=((observation.observation_id, "Greece"),),
    )
    resolved = resolve_country_evidence(company)
    assert resolved.country == "GR"
    assert resolved.country_evidence_id == observation.observation_id
    assert company.country is None


def test_hiring_locations_ambiguous_labels_and_conflicting_sources_do_not_invent_country():
    company = Store().company
    observation = replace(
        company.observations[0],
        description="Technical role in Greece.\ncategory: Greece",
    )
    assert (
        resolve_country_evidence(
            replace(
                company,
                observations=(observation,),
                source_countries=((observation.observation_id, "Greece"),),
            )
        ).country
        is None
    )
    observation = replace(observation, source="eu_startups")
    other = replace(
        observation,
        observation_id=uuid4(),
        description="Technical work.\ncategory: Germany",
    )
    conflicting = replace(
        company,
        observations=(observation, other),
        source_countries=(
            (observation.observation_id, "Greece"),
            (other.observation_id, "Germany"),
        ),
    )
    assert resolve_country_evidence(conflicting).country is None
    assert (
        resolve_country_evidence(replace(conflicting, country="USA")).country == "USA"
    )

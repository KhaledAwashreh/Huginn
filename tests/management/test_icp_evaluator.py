from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.application.services.icp_evaluation import evaluate_icp
from huginn.management.domain.entities.ideal_client_profile import IdealClientProfile


class CandidateSpy:
    def __init__(self):
        self.criteria = []

    def find_candidates(self, criteria):
        self.criteria.append(criteria)
        return ["candidate"]


def profile(**updates):
    fields = {
        "id": uuid4(),
        "user_id": uuid4(),
        "name": "ICP",
        "industries": ({"name": "SaaS"}, {"name": "Fintech"}),
        "company_sizes": ({"band": "0-10"}, {"band": "1001+"}),
        "geographies": (
            {"kind": "country", "value": "Germany"},
            {"kind": "country", "value": "Netherlands"},
        ),
        "exclusions": ({"kind": "industry", "name": "Gambling"},),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    fields.update(updates)
    return IdealClientProfile(**fields)


@pytest.mark.parametrize("dimension", ["industries", "company_sizes", "geographies"])
def test_empty_positive_dimension_returns_before_candidate_repository_call(dimension):
    spy = CandidateSpy()
    assert evaluate_icp(profile(**{dimension: ()}), spy) == []
    assert spy.criteria == []


def test_complete_icp_passes_flat_or_dimensions_and_global_exclusions():
    spy = CandidateSpy()
    criteria_profile = profile()

    assert evaluate_icp(criteria_profile, spy) == ["candidate"]
    [criteria] = spy.criteria
    assert criteria.industries == criteria_profile.industries
    assert criteria.company_sizes == criteria_profile.company_sizes
    assert criteria.geographies == criteria_profile.geographies
    assert criteria.exclusions == criteria_profile.exclusions
    assert (
        len(criteria.industries)
        == len(criteria.company_sizes)
        == len(criteria.geographies)
        == 2
    )
    assert not hasattr(criteria, "combinations")

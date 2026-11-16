import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from huginn.management.application.policies.recommendation_company_facts import (
    snapshot_recommendation_company,
)
from huginn.management.application.read_models.recommendation_profile import (
    RecommendationProfile,
)
from huginn.management.application.services.recommendation_offer_selection import (
    load_current_offer_selection,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.errors.errors import ConflictError, NotFoundError
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.domain.value_objects.strategy_assessment_snapshot import (
    StrategyAssessmentSnapshot,
)
from huginn.matchmaking.domain.policies.business_company_fit import assess_company_fit
from tests.management.application.recommendation_fixtures import recommendation_company

NOW = datetime(2026, 11, 14, tzinfo=UTC)


def _selection():
    company = recommendation_company()
    business_id, owner_id, recommendation_id, revision_id = (uuid4() for _ in range(4))
    strategy_id, offering_id, icp_id = (uuid4() for _ in range(3))
    icp = {
        "id": str(icp_id),
        "industries": [],
        "company_sizes": [],
        "geographies": [],
        "exclusions": [],
    }
    profile_snapshot = {
        "strategy": {"id": str(strategy_id)},
        "offering": {"id": str(offering_id)},
        "icp": icp,
    }
    fit = assess_company_fit(
        company.company_id,
        company.business_sector,
        company.company_scale,
        company.country,
        icp,
    )
    assessment = StrategyAssessmentSnapshot(
        strategy_id,
        offering_id,
        icp_id,
        JsonSnapshot(profile_snapshot["strategy"]),
        JsonSnapshot(profile_snapshot["offering"]),
        JsonSnapshot(icp),
        JsonSnapshot(
            {
                "company_facts": snapshot_recommendation_company(company),
                "icp_fit": dict(fit.dimensions),
            }
        ),
    )
    revision = AssessmentRevision(
        revision_id,
        recommendation_id,
        business_id,
        company.company_id,
        1,
        NOW,
        (assessment,),
        JsonSnapshot({}),
        (),
        (),
        ("test-policy",),
    )
    recommendation = Recommendation(
        recommendation_id,
        business_id,
        company.company_id,
        RecommendationStatus("open"),
        NOW,
        NOW,
        current_revision_id=revision_id,
    )
    records = SimpleNamespace(
        recommendation=recommendation, revision=revision, company=company
    )
    work = SimpleNamespace(
        recommendations=SimpleNamespace(
            get_owned=lambda business, identifier: (
                records.recommendation
                if business == business_id and identifier == recommendation_id
                else None
            )
        ),
        assessment_revisions=SimpleNamespace(
            get_owned=lambda business, identifier, revision: (
                records.revision
                if business == business_id
                and identifier == recommendation_id
                and revision == revision_id
                else None
            )
        ),
    )
    source = SimpleNamespace(
        current_company_for_revision=lambda revision, as_of: records.company,
        profile=lambda owner, strategy: (
            RecommendationProfile(strategy_id, json.dumps(profile_snapshot), "")
            if owner == owner_id and strategy == strategy_id
            else None
        ),
    )
    return (
        records,
        work,
        source,
        (business_id, owner_id, recommendation_id, revision_id, NOW),
    )


def test_owned_current_revision_is_authority_without_generation_receipt_json():
    records, work, source, args = _selection()
    selection = load_current_offer_selection(work, source, *args)
    assert selection.recommendation == records.recommendation
    assert selection.revision == records.revision
    assert selection.company == records.company


@pytest.mark.parametrize("argument", (0, 1, 2, 3))
def test_offer_selection_cannot_forge_owner_or_recommendation_membership(argument):
    _, work, source, args = _selection()
    args = list(args)
    args[argument] = uuid4()
    with pytest.raises(NotFoundError if argument != 1 else ConflictError):
        load_current_offer_selection(work, source, *args)


@pytest.mark.parametrize(
    "change",
    (
        "old_revision",
        "other_business",
        "other_company",
        "future_revision",
        "changed_evidence",
        "changed_configuration",
    ),
)
def test_offer_selection_revalidates_current_revision_and_source_inputs(change):
    records, work, source, args = _selection()
    if change == "old_revision":
        records.recommendation = replace(
            records.recommendation, current_revision_id=uuid4()
        )
    elif change == "other_business":
        records.revision = replace(records.revision, business_id=uuid4())
    elif change == "other_company":
        records.revision = replace(records.revision, company_id=uuid4())
    elif change == "future_revision":
        records.revision = replace(
            records.revision, assessed_at=NOW + timedelta(seconds=1)
        )
    elif change == "changed_evidence":
        records.company = None
    elif change == "changed_configuration":
        source.profile = lambda *args: None
    with pytest.raises(ConflictError):
        load_current_offer_selection(work, source, *args)

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.domain.value_objects.strategy_assessment_snapshot import (
    StrategyAssessmentSnapshot,
)


def test_revision_keeps_multiple_independent_strategy_assessments_and_frozen_context():
    business_id, company_id = uuid4(), uuid4()
    strategy_a, strategy_b = uuid4(), uuid4()
    profile = {"headline": "Engineer", "skills": [{"name": "Python"}]}
    snapshot_a = {"name": "Strategy A", "offering": {"name": "Build"}}
    snapshot_b = {"name": "Strategy B", "offering": {"name": "Advise"}}
    evidence = [{"observation_id": str(uuid4()), "quote": "Hiring now"}]
    revision = AssessmentRevision(
        id=uuid4(),
        recommendation_id=uuid4(),
        business_id=business_id,
        company_id=company_id,
        revision_number=1,
        assessed_at=datetime(2027, 1, 1, tzinfo=UTC),
        strategy_assessments=(
            StrategyAssessmentSnapshot(
                strategy_id=strategy_a,
                offering_id=uuid4(),
                ideal_client_profile_id=uuid4(),
                strategy_snapshot=snapshot_a,
                offering_snapshot={"name": "Build"},
                ideal_client_profile_snapshot={"industries": [{"name": "SaaS"}]},
                assessment_snapshot={"score": 72, "confidence": "medium"},
            ),
            StrategyAssessmentSnapshot(
                strategy_id=strategy_b,
                offering_id=uuid4(),
                ideal_client_profile_id=uuid4(),
                strategy_snapshot=snapshot_b,
                offering_snapshot={"name": "Advise"},
                ideal_client_profile_snapshot={"industries": [{"name": "Fintech"}]},
                assessment_snapshot={"score": 39, "confidence": "low"},
            ),
        ),
        professional_profile_snapshot=profile,
        evidence_snapshots=tuple(evidence),
        evidence_observation_ids=(uuid4(),),
        policy_versions=("company-fit-v1", "research-ranking-v1"),
    )
    profile["skills"][0]["name"] = "Changed"
    snapshot_a["offering"]["name"] = "Changed"
    evidence[0]["quote"] = "Changed"
    assert len(revision.strategy_assessments) == 2
    assert revision.strategy_assessments[0].assessment_snapshot.value["score"] == 72
    assert revision.professional_profile_snapshot.value["skills"][0]["name"] == "Python"
    assert (
        revision.strategy_assessments[0].strategy_snapshot.value["offering"]["name"]
        == "Build"
    )
    assert revision.evidence_snapshots[0].value["quote"] == "Hiring now"
    with pytest.raises(TypeError):
        revision.professional_profile_snapshot.value["headline"] = "Changed"


def test_revision_requires_unique_strategy_associations_and_positive_sequence():
    strategy_id = uuid4()
    association = StrategyAssessmentSnapshot(
        strategy_id,
        uuid4(),
        uuid4(),
        {"name": "A"},
        {"name": "B"},
        {"industry": "SaaS"},
        {"score": 1},
    )
    args = {
        "id": uuid4(),
        "recommendation_id": uuid4(),
        "business_id": uuid4(),
        "company_id": uuid4(),
        "revision_number": 1,
        "assessed_at": datetime(2027, 1, 1, tzinfo=UTC),
        "strategy_assessments": (association, association),
        "professional_profile_snapshot": {},
        "evidence_snapshots": (),
        "evidence_observation_ids": (),
        "policy_versions": ("v1",),
    }
    with pytest.raises(ValidationDomainError):
        AssessmentRevision(**args)
    args["strategy_assessments"] = (association,)
    args["revision_number"] = 0
    with pytest.raises(ValidationDomainError):
        AssessmentRevision(**args)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_json_snapshot_rejects_non_finite_numbers_recursively(value):
    with pytest.raises(ValidationDomainError):
        JsonSnapshot({"nested": [{"score": value}]})


def test_json_snapshot_exports_detached_json_and_roundtrips_without_mutating_snapshot():
    original = {"profile": {"skills": [{"name": "Python"}]}}
    snapshot = JsonSnapshot(original)
    exported = snapshot.to_json_object()
    roundtripped = JsonSnapshot(json.loads(json.dumps(exported)))
    exported["profile"]["skills"][0]["name"] = "Edited export"
    assert roundtripped.value["profile"]["skills"][0]["name"] == "Python"
    assert snapshot.value["profile"]["skills"][0]["name"] == "Python"

"""Shared valid Business-owned recommendation and prospect fixtures."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.entities.prospect_origin import ProspectOrigin
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.value_objects.activity_kind import ActivityKind
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.domain.value_objects.strategy_assessment_snapshot import (
    StrategyAssessmentSnapshot,
)
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.assessment_revision import (
    PostgresAssessmentRevisionRepository,
)
from huginn.management.persistence.repositories.recommendation import (
    PostgresRecommendationRepository,
)


@dataclass(frozen=True)
class ProspectingIdentity:
    account_id: UUID
    owner_user_id: UUID
    business_id: UUID
    company_id: UUID


def seed_prospecting_owner_company(connection) -> ProspectingIdentity:
    """Insert one isolated owner, Business, cadence row, and minimal Gold company."""
    account_id = connection.execute(
        "INSERT INTO operational.accounts(username,password_hash) "
        "VALUES (%s,'fixture-hash') RETURNING id",
        (f"prospecting-{uuid4()}@example.test",),
    ).fetchone()[0]
    owner_user_id = connection.execute(
        "INSERT INTO operational.users "
        "(account_id,first_name,last_name,email,phone_number,country_of_residence) "
        "VALUES (%s,'Ada','Lovelace',%s,'+12025550123','US') RETURNING id",
        (account_id, f"{uuid4()}@example.test"),
    ).fetchone()[0]
    business_id = connection.execute(
        "INSERT INTO operational.businesses(owner_user_id) VALUES (%s) RETURNING id",
        (owner_user_id,),
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO operational.business_recommendation_preferences(business_id) "
        "VALUES (%s)",
        (business_id,),
    )
    company_id = connection.execute(
        "INSERT INTO gold.company(domain,name) VALUES (%s,'Prospecting Fixture') "
        "RETURNING id",
        (f"{uuid4()}.example.test",),
    ).fetchone()[0]
    return ProspectingIdentity(account_id, owner_user_id, business_id, company_id)


def valid_recommendation(
    identity: ProspectingIdentity,
    *,
    recommendation_id: UUID | None = None,
    current_revision_id: UUID | None = None,
    status: RecommendationStatus | None = None,
    at: datetime | None = None,
) -> Recommendation:
    instant = at or datetime.now(UTC)
    return Recommendation(
        id=recommendation_id or uuid4(),
        business_id=identity.business_id,
        company_id=identity.company_id,
        status=status or RecommendationStatus("open"),
        created_at=instant,
        updated_at=instant,
        current_revision_id=current_revision_id,
    )


def valid_assessment_revision(
    identity: ProspectingIdentity,
    recommendation: Recommendation,
    *,
    revision_id: UUID | None = None,
    revision_number: int = 1,
    at: datetime | None = None,
) -> AssessmentRevision:
    instant = at or datetime.now(UTC)
    strategy_ids = (uuid4(), uuid4())
    offering_ids = (uuid4(), uuid4())
    profile_ids = (uuid4(), uuid4())
    associations = tuple(
        StrategyAssessmentSnapshot(
            strategy_id=strategy_id,
            offering_id=offering_id,
            ideal_client_profile_id=profile_id,
            strategy_snapshot=JsonSnapshot(
                {"name": f"Strategy {index + 1}", "active": True}
            ),
            offering_snapshot=JsonSnapshot(
                {"name": f"Offering {index + 1}", "description": "Research"}
            ),
            ideal_client_profile_snapshot=JsonSnapshot(
                {"name": f"ICP {index + 1}", "countries": ["US"]}
            ),
            assessment_snapshot=JsonSnapshot(
                {"score": 71 - index, "fit": "qualified", "reasons": ["sector"]}
            ),
        )
        for index, (strategy_id, offering_id, profile_id) in enumerate(
            zip(strategy_ids, offering_ids, profile_ids, strict=True)
        )
    )
    observation_ids = (uuid4(), uuid4())
    return AssessmentRevision(
        id=revision_id or uuid4(),
        recommendation_id=recommendation.id,
        business_id=identity.business_id,
        company_id=identity.company_id,
        revision_number=revision_number,
        assessed_at=instant,
        strategy_assessments=associations,
        professional_profile_snapshot=JsonSnapshot(
            {"headline": "Independent consultant", "skills": [{"name": "research"}]}
        ),
        evidence_snapshots=(
            JsonSnapshot({"source": "yc", "quote": "Hiring data analysts"}),
            JsonSnapshot({"source": "hn", "quote": "Seed round announced"}),
        ),
        evidence_observation_ids=observation_ids,
        policy_versions=("company-fit-v1", "lexical-fit-v1"),
        evaluation_seed="fixture-seed-v1",
        assessed_by_user_id=identity.owner_user_id,
    )


def valid_prospect(
    identity: ProspectingIdentity,
    *,
    prospect_id: UUID | None = None,
    stage: ProspectStage | None = None,
    at: datetime | None = None,
) -> Prospect:
    instant = at or datetime.now(UTC)
    return Prospect(
        id=prospect_id or uuid4(),
        business_id=identity.business_id,
        company_id=identity.company_id,
        stage=stage or ProspectStage("saved"),
        created_at=instant,
        updated_at=instant,
        notes="Initial prospect note",
    )


def valid_prospect_origin(
    identity: ProspectingIdentity,
    recommendation: Recommendation,
    revision: AssessmentRevision,
    prospect: Prospect,
    *,
    origin_id: UUID | None = None,
    at: datetime | None = None,
) -> ProspectOrigin:
    return ProspectOrigin(
        id=origin_id or uuid4(),
        business_id=identity.business_id,
        company_id=identity.company_id,
        prospect_id=prospect.id,
        recommendation_id=recommendation.id,
        assessment_revision_id=revision.id,
        created_by_user_id=identity.owner_user_id,
        created_at=at or datetime.now(UTC),
    )


def valid_prospect_activity(
    identity: ProspectingIdentity,
    prospect: Prospect,
    *,
    origin_id: UUID | None = None,
    kind: ActivityKind | None = None,
    activity_id: UUID | None = None,
    correction_of_id: UUID | None = None,
    at: datetime | None = None,
) -> ProspectActivity:
    activity_kind = kind or ActivityKind(
        "prospect_saved" if origin_id else "note_added"
    )
    payload: dict[str, object] = {"note": "Discuss the current hiring plan"}
    if origin_id is not None:
        payload["origin_id"] = str(origin_id)
    if activity_kind.value == "correction":
        payload = {"prior": "old", "replacement": "corrected"}
    instant = at or datetime.now(UTC)
    return ProspectActivity(
        id=activity_id or uuid4(),
        business_id=identity.business_id,
        prospect_id=prospect.id,
        actor_user_id=identity.owner_user_id,
        kind=activity_kind,
        occurred_at=instant,
        recorded_at=instant,
        payload=JsonSnapshot(payload),
        correction_of_id=correction_of_id,
    )


def valid_command_receipt(
    identity: ProspectingIdentity,
    *,
    resource_id: UUID,
    resource_version: int = 1,
    scope: str = "save_recommendation",
    key: str | None = None,
    payload_fingerprint: str = "a" * 64,
    result_snapshot: JsonSnapshot | None = None,
    at: datetime | None = None,
) -> CommandReceipt:
    return CommandReceipt(
        business_id=identity.business_id,
        scope=scope,
        identity=CommandIdentity(key or f"fixture-{uuid4()}", payload_fingerprint),
        resource_kind="prospect",
        resource_id=resource_id,
        resource_version=resource_version,
        result_snapshot=result_snapshot
        or JsonSnapshot({"id": str(resource_id), "version": resource_version}),
        recorded_at=at or datetime.now(UTC),
    )


def seed_owned_recommendation_revision(connection, identity=None):
    """Create an open recommendation and selected complete assessment revision.

    The caller owns the transaction and may supply a previously seeded owner and
    company to share Business identity with related repository fixtures.
    """
    identity = identity or seed_prospecting_owner_company(connection)
    session = PsycopgDatabaseSession(connection)
    recommendations = PostgresRecommendationRepository(session)
    revisions = PostgresAssessmentRevisionRepository(session)
    recommendation = recommendations.create_open(valid_recommendation(identity))
    revision = valid_assessment_revision(identity, recommendation)
    revisions.append(revision)
    recommendation = recommendations.select_current_revision(
        identity.business_id,
        recommendation.id,
        revision.id,
        recommendation.version,
    )
    return identity, recommendation, revision

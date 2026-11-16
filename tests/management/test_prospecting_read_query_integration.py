from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from huginn.management.application.requests.list_prospecting_request import (
    ListProspectingRequest,
)
from huginn.management.application.requests.save_recommendation_request import (
    SaveRecommendationRequest,
)
from huginn.management.application.services.prospecting_read_service import (
    ProspectingReadService,
)
from huginn.management.application.services.save_recommendation_service import (
    SaveRecommendationService,
)
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.prospect_stage import ProspectStage
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from huginn.management.persistence.queries.prospecting_query import (
    PostgresProspectingQuery,
)
from huginn.management.persistence.repositories.recommendation_generation import (
    PostgresRecommendationGenerationSource,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_owned_recommendation_revision,
)


def _seed(connection, name, identity=None):
    if identity is not None:
        company_id = connection.execute(
            "INSERT INTO gold.company(domain,name) VALUES (%s,%s) RETURNING id",
            (f"{uuid4()}.example.test", name),
        ).fetchone()[0]
        identity = replace(identity, company_id=company_id)
    identity, rec, rev = seed_owned_recommendation_revision(connection, identity)
    connection.execute(
        "UPDATE gold.company SET name=%s WHERE id=%s", (name, identity.company_id)
    )
    return identity, rec, rev


def _work(database_url, *, read_only=False):
    return PostgresProspectingUnitOfWork(
        ManagementConnectionFactory(database_url), read_only=read_only
    )


def _service(database_url):
    return ProspectingReadService(
        lambda: _work(database_url, read_only=True),
        query_factory=lambda work: PostgresProspectingQuery(
            work, PostgresRecommendationGenerationSource(work.connection)
        ),
    )


def _principal(identity):
    return Principal(identity.account_id, identity.owner_user_id)


def _snapshot(connection, business_id):
    return {
        table: connection.execute(
            f"SELECT to_jsonb(t) FROM operational.{table} t WHERE business_id=%s ORDER BY to_jsonb(t)::text",
            (business_id,),
        ).fetchall()
        for table in (
            "recommendations",
            "assessment_revisions",
            "offer_cycles",
            "offer_cycle_events",
            "prospects",
            "prospect_origins",
            "prospect_activities",
            "suppression_blocks",
            "command_receipts",
        )
    }


def test_recommendation_search_filters_full_owned_dataset_before_pagination(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity, alpha, _ = _seed(connection, "Alpha")
        target_identity, target, _ = _seed(connection, "Target_100%", identity)
        _, beta, _ = _seed(connection, "Beta", identity)
        foreign, _, foreign_revision = _seed(connection, "Target_100%")
    service = _service(management_database_url)
    first = service.list_recommendations(
        _principal(identity), ListProspectingRequest(limit=1)
    )
    assert first.has_more is True
    target_name = (
        "Alpha" if first.items[0].recommendation.id == target.id else "Target_100%"
    )
    target_id = alpha.id if target_name == "Alpha" else target.id
    assert target_id != first.items[0].recommendation.id
    found = service.list_recommendations(
        _principal(identity),
        ListProspectingRequest(search=target_name.upper(), limit=1),
    )
    assert tuple(view.recommendation.id for view in found.items) == (target_id,)
    assert found.has_more is False
    for literal in ("100%", "_"):
        found = service.list_recommendations(
            _principal(identity), ListProspectingRequest(search=literal)
        )
        assert tuple(view.recommendation.id for view in found.items) == (target.id,)
    domain = service.get_recommendation(_principal(identity), target.id).company.domain
    assert (
        service.list_recommendations(
            _principal(identity), ListProspectingRequest(search=domain)
        )
        .items[0]
        .recommendation.id
        == target.id
    )
    with pytest.raises(NotFoundError):
        service.get_recommendation(_principal(foreign), beta.id)
    with pytest.raises(NotFoundError):
        service.get_recommendation(
            _principal(identity), target.id, assessment_revision_id=foreign_revision.id
        )
    assert target_identity.business_id == identity.business_id


def test_historical_save_hides_another_open_occurrence_but_preserves_both_reads(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity, old, revision = _seed(connection, "Historical")
    with _work(management_database_url) as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        rejected = work.recommendations.resolve_owned(
            identity.business_id,
            old.id,
            old.version,
            RecommendationStatus("rejected"),
            identity.owner_user_id,
            datetime.now(UTC),
            "Original rejection",
        )
        work.commit()
    with psycopg.connect(management_database_url) as connection:
        _, current, _ = seed_owned_recommendation_revision(connection, identity)
    saved = SaveRecommendationService(lambda: _work(management_database_url)).execute(
        _principal(identity),
        SaveRecommendationRequest(old.id, revision.id, "save-history"),
    )
    service = _service(management_database_url)
    assert (
        service.list_recommendations(
            _principal(identity), ListProspectingRequest()
        ).items
        == ()
    )
    history = service.get_recommendation(_principal(identity), old.id)
    assert history.recommendation == rejected
    assert history.assessment == revision
    assert history.prospect.id == saved.prospect_id
    assert history.current_eligibility == "historical"
    other = service.get_recommendation(_principal(identity), current.id)
    assert other.recommendation.status.value == "open"
    assert other.prospect.id == saved.prospect_id
    assert "relationship" in other.selection_blockers
    assert other.current_eligibility == "blocked"
    resolved = service.list_recommendations(
        _principal(identity),
        ListProspectingRequest(),
        status=RecommendationStatus("rejected"),
    )
    assert tuple(view.recommendation.id for view in resolved.items) == (old.id,)


def test_prospect_search_and_stage_filter_preserve_exact_origin_explanations(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity, first, first_revision = _seed(connection, "First prospect")
        other, second, second_revision = _seed(connection, "Second prospect", identity)
    saves = SaveRecommendationService(lambda: _work(management_database_url))
    first_saved = saves.execute(
        _principal(identity),
        SaveRecommendationRequest(first.id, first_revision.id, "save-first"),
    )
    second_saved = saves.execute(
        _principal(identity),
        SaveRecommendationRequest(second.id, second_revision.id, "save-second"),
    )
    with _work(management_database_url) as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        prospect = work.prospects.get_owned(
            identity.business_id, first_saved.prospect_id
        )
        work.prospects.update_owned(
            identity.business_id,
            prospect.id,
            prospect.version,
            replace(
                prospect,
                stage=ProspectStage("contacted"),
                version=2,
                updated_at=datetime.now(UTC),
            ),
        )
        work.commit()
    service = _service(management_database_url)
    matches = service.list_prospects(
        _principal(identity),
        ListProspectingRequest(search="FIRST", limit=1),
        stage=ProspectStage("contacted"),
    )
    assert tuple(view.prospect.id for view in matches.items) == (
        first_saved.prospect_id,
    )
    assert matches.has_more is False
    assert (
        service.list_prospects(
            _principal(identity),
            ListProspectingRequest(search="FIRST"),
            stage=ProspectStage("saved"),
        ).items
        == ()
    )
    detail = service.get_prospect(_principal(identity), second_saved.prospect_id)
    assert detail.company.id == other.company_id
    assert detail.origins[0].origin.assessment_revision_id == second_revision.id
    assert detail.origins[0].assessment == second_revision
    assert detail.activities[0].kind.value == "prospect_saved"


def test_unsaved_hidden_suppressions_have_company_identity_and_independent_blockers(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity, recommendation, _ = _seed(connection, "Hidden unsaved")
        foreign, _, _ = _seed(connection, "Foreign hidden")
    now = datetime.now(UTC)
    with _work(management_database_url) as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        work.recommendations.resolve_owned(
            identity.business_id,
            recommendation.id,
            recommendation.version,
            RecommendationStatus("rejected"),
            identity.owner_user_id,
            now,
            "Not relevant",
        )
        blocks = tuple(
            work.suppression_blocks.append(
                SuppressionBlock(
                    uuid4(),
                    identity.business_id,
                    identity.company_id,
                    SuppressionKind(kind),
                    now,
                    created_by_user_id=identity.owner_user_id,
                    expires_at=expiry,
                )
            )
            for kind, expiry in (
                ("rejection", None),
                ("pause", now + timedelta(days=3)),
                ("cooldown", now + timedelta(days=30)),
            )
        )
        work.commit()
    page = _service(management_database_url).list_manageable_suppressions(
        _principal(identity), ListProspectingRequest(search="hidden")
    )
    assert len(page.items) == 1
    view = page.items[0]
    assert view.company.id == identity.company_id
    assert view.company.name == "Hidden unsaved"
    assert view.prospect is None
    assert set(view.active_blocks) == set(blocks)
    assert set(view.selection_blockers) == {"paused", "cooldown", "rejected"}
    assert (
        _service(management_database_url)
        .list_manageable_suppressions(_principal(foreign), ListProspectingRequest())
        .items
        == ()
    )


def test_routine_reads_preserve_all_history_with_unavailable_current_evidence(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity, recommendation, revision = _seed(connection, "Retained history")
        before = _snapshot(connection, identity.business_id)
    service = _service(management_database_url)
    for _ in range(2):
        view = service.get_recommendation(_principal(identity), recommendation.id)
        assert view.assessment == revision
        assert view.evidence_state == "unavailable"
        assert view.current_eligibility == "unavailable"
        assert view.recommendation.first_presented_at is None
        service.list_recommendations(_principal(identity), ListProspectingRequest())
        service.list_prospects(_principal(identity), ListProspectingRequest())
        service.list_manageable_suppressions(
            _principal(identity), ListProspectingRequest()
        )
    with psycopg.connect(management_database_url) as connection:
        assert _snapshot(connection, identity.business_id) == before


def test_exact_historical_revision_reads_keep_current_context_separate(
    management_database_url,
):
    from tests.management.persistence.prospecting_fixtures import (
        valid_assessment_revision,
    )

    with psycopg.connect(management_database_url) as connection:
        identity, recommendation, original = _seed(connection, "Revision history")
    with _work(management_database_url) as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        newer = work.assessment_revisions.append(
            valid_assessment_revision(identity, recommendation, revision_number=2)
        )
        current = work.recommendations.select_current_revision(
            identity.business_id, recommendation.id, newer.id, recommendation.version
        )
        work.commit()
    service = _service(management_database_url)
    old_view = service.get_recommendation(
        _principal(identity), recommendation.id, assessment_revision_id=original.id
    )
    assert old_view.assessment == original
    assert old_view.recommendation == current
    assert old_view.recommendation.current_revision_id == newer.id
    assert (
        service.get_recommendation(_principal(identity), recommendation.id).assessment
        == newer
    )
    assert service.list_assessments(_principal(identity), recommendation.id) == (
        original,
        newer,
    )


def test_manageable_read_and_explicit_resume_need_no_prospect_or_new_generation(
    management_database_url,
):
    from huginn.management.application.requests.cancel_recommendation_pause_request import (
        CancelRecommendationPauseRequest,
    )
    from huginn.management.application.requests.reverse_recommendation_rejection_request import (
        ReverseRecommendationRejectionRequest,
    )
    from huginn.management.application.services.cancel_recommendation_pause_service import (
        CancelRecommendationPauseService,
    )
    from huginn.management.application.services.reverse_recommendation_rejection_service import (
        ReverseRecommendationRejectionService,
    )

    with psycopg.connect(management_database_url) as connection:
        identity, recommendation, _ = _seed(connection, "Manage hidden company")
    now = datetime.now(UTC)
    with _work(management_database_url) as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        rejected = work.recommendations.resolve_owned(
            identity.business_id,
            recommendation.id,
            recommendation.version,
            RecommendationStatus("rejected"),
            identity.owner_user_id,
            now,
            "Original decision",
        )
        for kind, expiry in (
            ("rejection", None),
            ("pause", now + timedelta(days=2)),
            ("cooldown", now + timedelta(days=30)),
        ):
            work.suppression_blocks.append(
                SuppressionBlock(
                    uuid4(),
                    identity.business_id,
                    identity.company_id,
                    SuppressionKind(kind),
                    now,
                    created_by_user_id=identity.owner_user_id,
                    expires_at=expiry,
                )
            )
        work.commit()
    service = _service(management_database_url)
    entry = service.list_manageable_suppressions(
        _principal(identity), ListProspectingRequest()
    ).items[0]
    block = next(
        block for block in entry.active_blocks if block.kind.value == "rejection"
    )
    reversed_result = ReverseRecommendationRejectionService(
        lambda: _work(management_database_url)
    ).execute(
        _principal(identity),
        ReverseRecommendationRejectionRequest(
            block.id, block.version, "reverse-hidden"
        ),
    )
    assert set(reversed_result.remaining_blockers) == {"paused", "cooldown"}
    entry = service.list_manageable_suppressions(
        _principal(identity), ListProspectingRequest()
    ).items[0]
    pause = next(block for block in entry.active_blocks if block.kind.value == "pause")
    resumed = CancelRecommendationPauseService(
        lambda: _work(management_database_url)
    ).execute(
        _principal(identity),
        CancelRecommendationPauseRequest(pause.id, pause.version, "resume-hidden"),
    )
    assert resumed.remaining_blockers == ("cooldown",)
    assert (
        service.list_manageable_suppressions(
            _principal(identity), ListProspectingRequest()
        ).items
        == ()
    )
    with _work(management_database_url, read_only=True) as work:
        assert (
            work.recommendations.get_owned(identity.business_id, recommendation.id)
            == rejected
        )
        assert (
            work.prospects.get_by_business_company(
                identity.business_id, identity.company_id
            )
            is None
        )
        history = work.suppression_blocks.list_history(
            identity.business_id, identity.company_id
        )
        assert len(history) == 3
        assert (
            sum(block.cleared_by_user_id == identity.owner_user_id for block in history)
            == 2
        )
        assert (
            work.connection.execute(
                "SELECT count(*) FROM operational.recommendations WHERE business_id=%s",
                (identity.business_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            work.connection.execute(
                "SELECT count(*) FROM operational.command_receipts WHERE business_id=%s AND scope LIKE %s",
                (identity.business_id, "recommendation_generation:%"),
            ).fetchone()[0]
            == 0
        )

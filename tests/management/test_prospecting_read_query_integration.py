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
    from huginn.management.application.services.recommendation_decision_service import (
        RecommendationDecisionService,
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
    reversed_result = RecommendationDecisionService(
        lambda: _work(management_database_url)
    ).reverse_rejection(
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
    resumed = RecommendationDecisionService(
        lambda: _work(management_database_url)
    ).cancel_pause(
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


@pytest.mark.parametrize("limit", (1, 3))
def test_prospect_page_batches_all_saved_origins_without_history_or_owner_loss(
    management_database_url, limit
):
    from tests.management.persistence.prospecting_fixtures import (
        valid_assessment_revision,
        valid_prospect_origin,
    )

    with psycopg.connect(management_database_url) as connection:
        identity, recommendation, revision = _seed(connection, "Batch prospect 0")
        selections = [(identity, recommendation, revision)]
        for index in range(1, 3):
            selections.append(_seed(connection, f"Batch prospect {index}", identity))
        foreign, foreign_rec, foreign_revision = _seed(
            connection, "Batch prospect foreign"
        )
    saves = SaveRecommendationService(lambda: _work(management_database_url))
    expected = {}
    for index, (owner, rec, selected) in enumerate(
        selections + [(foreign, foreign_rec, foreign_revision)]
    ):
        saved = saves.execute(
            _principal(owner),
            SaveRecommendationRequest(rec.id, selected.id, f"batch-save-{index}"),
        )
        with _work(management_database_url) as work:
            prospect = work.prospects.get_owned(owner.business_id, saved.prospect_id)
            newer = work.assessment_revisions.append(
                valid_assessment_revision(owner, rec, revision_number=2)
            )
            work.origins.append_if_absent(
                valid_prospect_origin(owner, rec, newer, prospect)
            )
            # Unsaved assessment history must not replace or enter saved origins.
            work.assessment_revisions.append(
                valid_assessment_revision(owner, rec, revision_number=3)
            )
            work.commit()
        if owner.business_id == identity.business_id:
            expected[saved.prospect_id] = (selected, newer)
    queries = []

    class CountingCursor(psycopg.Cursor):
        def execute(self, query, params=None, **kwargs):
            queries.append(str(query))
            return super().execute(query, params, **kwargs)

    def connect(database_url, **kwargs):
        return psycopg.connect(database_url, cursor_factory=CountingCursor, **kwargs)

    factory = ManagementConnectionFactory(management_database_url, connector=connect)
    with PostgresProspectingUnitOfWork(factory, read_only=True) as work:
        queries.clear()
        query = PostgresProspectingQuery(
            work, PostgresRecommendationGenerationSource(work.connection)
        )
        page = query.list_prospects(
            identity.business_id,
            ListProspectingRequest(limit=limit),
            None,
            datetime.now(UTC),
        )
        assert len(queries) <= 5, queries
        assert len(page.items) == limit
        assert page.has_more is (limit < 3)
        for view in page.items:
            assert (
                tuple(origin.assessment for origin in view.origins)
                == expected[view.prospect.id]
            )
            assert all(
                origin.recommendation.business_id == identity.business_id
                for origin in view.origins
            )
            assert view.activities is None
            assert view.current_source_context is None
        queries.clear()
        detail = query.get_prospect(
            identity.business_id, page.items[0].prospect.id, datetime.now(UTC)
        )
        assert len(queries) <= 7, queries
        assert detail.origins == page.items[0].origins
        assert detail.activities[0].kind.value == "prospect_saved"
        assert (
            work.prospects.get_many_owned(identity.business_id, (saved.prospect_id,))
            == ()
        )
        assert (
            work.origins.list_for_prospects(identity.business_id, (saved.prospect_id,))
            == ()
        )
        assert (
            work.recommendations.get_many_owned(identity.business_id, (foreign_rec.id,))
            == ()
        )
        assert (
            work.assessment_revisions.get_many_owned(
                identity.business_id, (foreign_revision.id,)
            )
            == ()
        )
        queries.clear()
        assert (
            query.list_prospects(
                identity.business_id,
                ListProspectingRequest(search="absent-target"),
                None,
                datetime.now(UTC),
            ).items
            == ()
        )
        assert len(queries) == 1
        assert (
            query.get_prospect(
                identity.business_id, saved.prospect_id, datetime.now(UTC)
            )
            is None
        )
    with psycopg.connect(management_database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.assessment_revisions WHERE business_id=%s",
                (identity.business_id,),
            ).fetchone()[0]
            == 9
        )


def test_batched_prospect_reads_preserve_captured_source_and_persisted_history(
    retained_management_database_url, monkeypatch
):
    from tests.management.persistence.retained_prospecting_fixtures import (
        generate_retained_brightroom_selection,
        seed_retained_brightroom_context,
    )

    context = seed_retained_brightroom_context(
        retained_management_database_url, monkeypatch
    )
    selection = generate_retained_brightroom_selection(context)
    with _work(context.database_url, read_only=True) as work:
        assessed = work.assessment_revisions.get_owned(
            context.business_id, selection.recommendation_id, selection.revision_id
        )
    saved = SaveRecommendationService(lambda: _work(context.database_url)).execute(
        context.principal,
        SaveRecommendationRequest(
            selection.recommendation_id, selection.revision_id, "save-captured-source"
        ),
    )
    with psycopg.connect(context.database_url) as connection:
        before = _snapshot(connection, context.business_id)
        stored_evidence = connection.execute(
            "SELECT evidence_snapshots FROM operational.assessment_revisions WHERE id=%s",
            (selection.revision_id,),
        ).fetchone()[0]
    service = _service(context.database_url)
    listing = service.list_prospects(context.principal, ListProspectingRequest())
    detail = service.get_prospect(context.principal, saved.prospect_id)
    assert len(listing.items) == 1
    assert listing.items[0].origins == detail.origins
    assert detail.origins[0].assessment == assessed
    evidence = [
        value.to_json_object()
        for value in detail.origins[0].assessment.evidence_snapshots
    ]
    assert evidence == stored_evidence
    assert evidence and all(
        value["source_url"] == context.listing_url for value in evidence
    )
    assert all(value["quote"] in value["description"] for value in evidence)
    assert detail.activities[0].kind.value == "prospect_saved"
    with psycopg.connect(context.database_url) as connection:
        assert _snapshot(connection, context.business_id) == before


def test_retained_prospect_reads_new_guarded_source_without_rewriting_saved_origin(
    retained_management_database_url, monkeypatch
):
    from huginn.config import Config
    from huginn.elt.materialization import build_eu_startups_materialization_stages
    from tests.management.persistence.retained_prospecting_fixtures import (
        generate_retained_brightroom_selection,
        seed_retained_brightroom_context,
    )

    context = seed_retained_brightroom_context(
        retained_management_database_url, monkeypatch
    )
    selection = generate_retained_brightroom_selection(context)
    saved = SaveRecommendationService(lambda: _work(context.database_url)).execute(
        context.principal,
        SaveRecommendationRequest(
            selection.recommendation_id, selection.revision_id, "save-current-context"
        ),
    )
    service = _service(context.database_url)
    original = service.get_prospect(context.principal, saved.prospect_id)
    assert original.current_source_context.evidence_state == "current"
    original_ids = {
        signal.observation_id for signal in original.current_source_context.signals
    }
    with psycopg.connect(context.database_url) as connection:
        before = _snapshot(connection, context.business_id)
        payload = connection.execute(
            "SELECT payload FROM bronze.web_scrape_ingest WHERE source='eu_startups' AND stable_id=%s",
            (context.stable_id,),
        ).fetchone()[0]
        # Controlled follow-up to the captured real source, through the same
        # ingestion/materialization boundary. No live upstream claim is made.
        payload["html"] = payload["html"].replace("Brightroom", "Brightroom current")
        connection.execute(
            "UPDATE bronze.web_scrape_ingest SET payload=%s,fetched_at=clock_timestamp() WHERE source='eu_startups' AND stable_id=%s",
            (psycopg.types.json.Jsonb(payload), context.stable_id),
        )
    unavailable = service.get_prospect(context.principal, saved.prospect_id)
    assert unavailable.current_source_context.evidence_state == "unavailable"
    assert unavailable.current_source_context.signals == ()
    assert unavailable.origins == original.origins
    stages = build_eu_startups_materialization_stages(
        Config(database_url=context.database_url, yc_algolia_api_key="test"),
        include_manual_review=False,
        resolve_eu_startups_only=True,
    )
    for stage in stages:
        stage.run()
    for _ in range(2):
        detail = service.get_prospect(context.principal, saved.prospect_id)
        current = detail.current_source_context
        assert current.evidence_state == "changed"
        assert len(current.signals) == 1
        signal = current.signals[0]
        assert signal.observation_id not in original_ids
        assert signal.source_url == context.listing_url
        assert signal.source == "eu_startups"
        assert "Brightroom current" in signal.description
        assert (
            signal.observed_at > original.current_source_context.signals[0].observed_at
        )
        assert detail.origins == original.origins
        assert (
            service.list_prospects(context.principal, ListProspectingRequest())
            .items[0]
            .current_source_context
            is None
        )
    with psycopg.connect(context.database_url) as connection:
        assert _snapshot(connection, context.business_id) == before
        persisted = connection.execute(
            "SELECT observation_id,source_url,description,observed_at,occurred_at FROM gold.current_source_evidence WHERE company_id=%s",
            (context.company_id,),
        ).fetchone()
        assert persisted == (
            signal.observation_id,
            signal.source_url,
            signal.description,
            signal.observed_at,
            signal.occurred_at,
        )
    from fastapi.testclient import TestClient

    from huginn.management.app import create_app
    from huginn.management.config import ManagementConfig
    from huginn.management.domain.entities.session import Session
    from huginn.management.presentation.api.dependencies.authentication import (
        AuthenticatedSession,
        get_authenticated_session,
    )
    from huginn.management.presentation.api.prospecting_mapping import prospect_response

    app = create_app(ManagementConfig(context.database_url, environment="test"))
    now = datetime.now(UTC)
    session = Session(uuid4(), context.account_id, "digest", "csrf", now, now, None)
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        context.principal, session, "opaque"
    )
    with TestClient(app) as client:
        response = client.get(f"/api/v1/prospects/{saved.prospect_id}")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["current_source_context"]["evidence_state"] == "changed"
        assert body["current_source_context"]["signals"][0]["observation_id"] == str(
            signal.observation_id
        )
        assert body["current_source_context"]["signals"][0][
            "observed_at"
        ] == signal.observed_at.isoformat().replace("+00:00", "Z")
        assert (
            body["origins"]
            == prospect_response(original).model_dump(mode="json")["origins"]
        )
    with psycopg.connect(context.database_url) as connection:
        assert _snapshot(connection, context.business_id) == before


def test_exact_revision_presentation_survives_repeat_generation_and_rereads(
    retained_management_database_url, monkeypatch
):
    from huginn.management.application.requests.confirm_recommendation_offer_request import (
        ConfirmRecommendationOfferRequest,
    )
    from huginn.management.application.requests.prepare_recommendation_offer_request import (
        PrepareRecommendationOfferRequest,
    )
    from huginn.management.application.services.recommendation_offer_service import (
        RecommendationOfferService,
    )
    from tests.management.persistence.retained_prospecting_fixtures import (
        generate_retained_brightroom_selection,
        seed_retained_brightroom_context,
    )

    context = seed_retained_brightroom_context(
        retained_management_database_url, monkeypatch
    )
    initial = generate_retained_brightroom_selection(context)

    def factory():
        return _work(context.database_url)

    kwargs = {
        "source_factory": PostgresRecommendationGenerationSource,
        "clock": lambda: context.current_time[0],
    }
    offers = RecommendationOfferService(factory, **kwargs)
    first_claim = offers.prepare(
        context.principal,
        PrepareRecommendationOfferRequest(
            initial.recommendation_id, initial.revision_id, "first-read-confirm"
        ),
    )
    first = offers.confirm(
        context.principal,
        ConfirmRecommendationOfferRequest(
            first_claim.offer_cycle_id, first_claim.claim_token
        ),
    )
    context.current_time[0] += timedelta(days=31)
    newer = generate_retained_brightroom_selection(context)
    assert newer.recommendation_id == initial.recommendation_id
    assert newer.revision_id != initial.revision_id
    for _ in range(2):
        service = _service(context.database_url)
        detail = service.get_recommendation(context.principal, newer.recommendation_id)
        assert detail.recommendation.first_presented_at == first.presented_at
        assert detail.assessment.id == newer.revision_id
        assert detail.assessment_presented_at is None
        assert (
            service.list_recommendations(context.principal, ListProspectingRequest())
            .items[0]
            .assessment_presented_at
            is None
        )
        historical = service.get_recommendation(
            context.principal,
            initial.recommendation_id,
            assessment_revision_id=initial.revision_id,
        )
        assert historical.assessment_presented_at == first.presented_at
    pending = offers.prepare(
        context.principal,
        PrepareRecommendationOfferRequest(
            newer.recommendation_id, newer.revision_id, "repeat-read-confirm"
        ),
    )
    assert (
        _service(context.database_url)
        .get_recommendation(context.principal, newer.recommendation_id)
        .assessment_presented_at
        is None
    )
    second = offers.confirm(
        context.principal,
        ConfirmRecommendationOfferRequest(pending.offer_cycle_id, pending.claim_token),
    )
    with psycopg.connect(context.database_url) as connection:
        before = _snapshot(connection, context.business_id)
    for _ in range(2):
        service = _service(context.database_url)
        assert (
            service.get_recommendation(
                context.principal, newer.recommendation_id
            ).assessment_presented_at
            == second.presented_at
        )
        assert (
            service.list_recommendations(context.principal, ListProspectingRequest())
            .items[0]
            .assessment_presented_at
            == second.presented_at
        )
        assert (
            service.get_recommendation(
                context.principal,
                initial.recommendation_id,
                assessment_revision_id=initial.revision_id,
            ).assessment_presented_at
            == first.presented_at
        )
    with psycopg.connect(context.database_url) as connection:
        assert _snapshot(connection, context.business_id) == before


@pytest.mark.parametrize("additional_count", (1, 51))
def test_prospect_context_detects_additional_current_sources_beyond_display_bound(
    retained_management_database_url, monkeypatch, additional_count
):
    from huginn.config import Config
    from huginn.elt.materialization import build_eu_startups_materialization_stages
    from tests.management.persistence.retained_prospecting_fixtures import (
        generate_retained_brightroom_selection,
        seed_retained_brightroom_context,
    )

    context = seed_retained_brightroom_context(
        retained_management_database_url, monkeypatch
    )
    selection = generate_retained_brightroom_selection(context)
    saved = SaveRecommendationService(lambda: _work(context.database_url)).execute(
        context.principal,
        SaveRecommendationRequest(
            selection.recommendation_id,
            selection.revision_id,
            "save-additional-context",
        ),
    )
    service = _service(context.database_url)
    original = service.get_prospect(context.principal, saved.prospect_id)
    original_ids = {
        signal.observation_id for signal in original.current_source_context.signals
    }
    with psycopg.connect(context.database_url) as connection:
        payload = connection.execute(
            "SELECT payload FROM bronze.web_scrape_ingest WHERE source='eu_startups' AND stable_id=%s",
            (context.stable_id,),
        ).fetchone()[0]
        # Additional controlled listings retain the captured source content and
        # explicit company website while entering through Bronze and normal ELT.
        for index in range(additional_count):
            stable_id = f"brightroom-additional-{index}"
            url = context.listing_url.replace("brightroom/", f"{stable_id}/")
            followup = {
                **payload,
                "url": url,
                "html": payload["html"].replace(context.listing_url, url),
            }
            connection.execute(
                "INSERT INTO bronze.web_scrape_ingest (source,stable_id,payload,content_hash,run_id) VALUES ('eu_startups',%s,%s,%s,%s)",
                (stable_id, psycopg.types.json.Jsonb(followup), uuid4().hex, uuid4()),
            )
    stages = build_eu_startups_materialization_stages(
        Config(database_url=context.database_url, yc_algolia_api_key="test"),
        include_manual_review=False,
        resolve_eu_startups_only=True,
    )
    for stage in stages:
        stage.run()
    detail = service.get_prospect(context.principal, saved.prospect_id)
    assert detail.current_source_context.evidence_state == "changed"
    assert len(detail.current_source_context.signals) == min(50, additional_count + 1)
    assert detail.current_source_context.has_more is (additional_count + 1 > 50)
    assert detail.origins == original.origins
    assert (
        service.get_prospect(
            context.principal, saved.prospect_id
        ).current_source_context
        == detail.current_source_context
    )
    with psycopg.connect(context.database_url) as connection:
        current_ids = {
            row[0]
            for row in connection.execute(
                "SELECT observation_id FROM gold.current_source_evidence WHERE company_id=%s",
                (context.company_id,),
            ).fetchall()
        }
        assert len(current_ids) == additional_count + 1
        assert original_ids < current_ids


@pytest.mark.parametrize("status", ("preparing", "sending", "unknown", "abandoned"))
def test_unconfirmed_offer_states_never_claim_revision_presentation(
    management_database_url, status
):
    from huginn.management.domain.entities.offer_cycle import OfferCycle
    from huginn.management.domain.value_objects.accepted_offer_cadence import (
        AcceptedOfferCadence,
    )
    from huginn.management.domain.value_objects.offer_cycle_status import (
        OfferCycleStatus,
    )

    now = datetime.now(UTC)
    with psycopg.connect(management_database_url) as connection:
        identity, recommendation, revision = _seed(connection, f"Unconfirmed {status}")
    with _work(management_database_url) as work:
        work.lock_business_company(identity.business_id, identity.company_id)
        cycle = work.offer_cycles.acquire_preparing(
            OfferCycle(
                uuid4(),
                identity.business_id,
                identity.company_id,
                recommendation.id,
                revision.id,
                f"read-{status}",
                "a" * 64,
                OfferCycleStatus("preparing"),
                now,
                now,
                claim_token="claim",
                lease_expires_at=now + timedelta(minutes=5),
            ),
            now=now,
            lease_expires_at=now + timedelta(minutes=5),
            claim_token="claim",
        )
        if status in {"sending", "unknown"}:
            started = now + timedelta(seconds=1)
            work.offer_cycles.mark_sending(
                identity.business_id,
                identity.company_id,
                cycle.id,
                "claim",
                started,
                AcceptedOfferCadence(30, now, started),
            )
        if status == "unknown":
            work.offer_cycles.settle_sending(
                identity.business_id,
                identity.company_id,
                cycle.id,
                "claim",
                "unknown",
                now + timedelta(seconds=2),
            )
        elif status == "abandoned":
            work.offer_cycles.abandon_preparing(
                identity.business_id,
                identity.company_id,
                cycle.id,
                "claim",
                identity.owner_user_id,
                "Never displayed",
                now + timedelta(seconds=1),
            )
        work.commit()
    with psycopg.connect(management_database_url) as connection:
        before = _snapshot(connection, identity.business_id)
    service = _service(management_database_url)
    assert (
        service.get_recommendation(
            _principal(identity), recommendation.id
        ).assessment_presented_at
        is None
    )
    assert (
        service.list_recommendations(_principal(identity), ListProspectingRequest())
        .items[0]
        .assessment_presented_at
        is None
    )
    with psycopg.connect(management_database_url) as connection:
        assert _snapshot(connection, identity.business_id) == before


def test_unassessed_recommendation_has_no_assessment_presentation(
    management_database_url,
):
    from tests.management.persistence.prospecting_fixtures import (
        seed_prospecting_owner_company,
        valid_recommendation,
    )

    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
    with _work(management_database_url) as work:
        recommendation = work.recommendations.create_open(
            valid_recommendation(identity)
        )
        work.commit()
    service = _service(management_database_url)
    view = service.get_recommendation(_principal(identity), recommendation.id)
    assert view.assessment is None
    assert view.assessment_presented_at is None
    assert (
        service.list_recommendations(_principal(identity), ListProspectingRequest())
        .items[0]
        .assessment_presented_at
        is None
    )

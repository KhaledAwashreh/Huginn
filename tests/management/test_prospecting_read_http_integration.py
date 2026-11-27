"""Actual persisted workflow reads through authenticated HTTP composition."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.session import Session
from huginn.management.domain.value_objects.common import Principal
from huginn.management.presentation.api.dependencies.authentication import (
    AuthenticatedSession,
    get_authenticated_session,
)
from huginn.management.security.tokens import digest_token
from tests.management.persistence.prospecting_fixtures import (
    seed_owned_recommendation_revision,
)


def _snapshot(connection):
    return {
        table: connection.execute(
            f"SELECT to_jsonb(t) FROM operational.{table} t ORDER BY to_jsonb(t)::text"
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
            "recommendation_assessment_feedback",
        )
    }


def test_retained_source_offer_http_records_only_explicit_confirmation(
    retained_management_database_url, monkeypatch
):
    from tests.management.persistence.retained_prospecting_fixtures import (
        generate_retained_brightroom_selection,
        seed_retained_brightroom_context,
    )

    context = seed_retained_brightroom_context(
        retained_management_database_url, monkeypatch
    )
    selected = generate_retained_brightroom_selection(context)
    app = create_app(
        ManagementConfig(retained_management_database_url, environment="test"),
        clock=lambda: context.current_time[0],
    )
    principal = context.principal
    now = context.current_time[0]
    session = Session(
        uuid4(), principal.account_id, "digest", digest_token("csrf"), now, now, None
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    with TestClient(app) as client:
        prepared = client.post(
            f"/api/v1/recommendations/{selected.recommendation_id}/offer-preparations",
            json={
                "assessment_revision_id": str(selected.revision_id),
                "request_key": str(uuid4()),
            },
            headers={"X-CSRF-Token": "csrf"},
        )
        assert prepared.status_code == 200, prepared.text
        assert prepared.json()["status"] == "preparing"
        token = prepared.json()["claim_token"]
        cycle = prepared.json()["offer_cycle_id"]
        with psycopg.connect(
            retained_management_database_url, autocommit=True
        ) as connection:
            before_read = _snapshot(connection)
            assert (
                connection.execute(
                    "SELECT first_presented_at FROM operational.recommendations WHERE id=%s",
                    (selected.recommendation_id,),
                ).fetchone()[0]
                is None
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM operational.suppression_blocks WHERE business_id=%s AND kind='cooldown'",
                    (context.business_id,),
                ).fetchone()[0]
                == 0
            )
            detail = client.get(
                f"/api/v1/recommendations/{selected.recommendation_id}",
                params={"assessment_revision_id": str(selected.revision_id)},
            )
            assert detail.status_code == 200, detail.text
            assert (
                detail.json()["assessment"]["evidence_snapshots"][0]["source_url"]
                == context.listing_url
            )
            assert _snapshot(connection) == before_read
        context.current_time[0] += timedelta(seconds=30)
        confirmed = client.post(
            f"/api/v1/recommendations/offer-preparations/{cycle}/confirm",
            json={"claim_token": token},
            headers={"X-CSRF-Token": "csrf"},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert (
            datetime.fromisoformat(confirmed.json()["presented_at"])
            == context.current_time[0]
        )
        assert datetime.fromisoformat(
            confirmed.json()["cooldown_expires_at"]
        ) == context.current_time[0] + timedelta(days=30)
        context.current_time[0] += timedelta(hours=1)
        replay = client.post(
            f"/api/v1/recommendations/offer-preparations/{cycle}/confirm",
            json={"claim_token": token},
            headers={"X-CSRF-Token": "csrf"},
        )
        assert replay.json() == confirmed.json()
        with psycopg.connect(
            retained_management_database_url, autocommit=True
        ) as connection:
            confirmed_rows = _snapshot(connection)
            assert connection.execute(
                "SELECT claim_token,presented_at FROM operational.offer_cycles WHERE id=%s",
                (cycle,),
            ).fetchone() == (
                None,
                datetime.fromisoformat(confirmed.json()["presented_at"]),
            )
            client.get(f"/api/v1/recommendations/{selected.recommendation_id}")
            assert _snapshot(connection) == confirmed_rows


def test_http_reads_preserve_stored_workflow_and_exact_revision_ownership(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity, rec, revision = seed_owned_recommendation_revision(connection)
        _, foreign_rec, foreign_revision = seed_owned_recommendation_revision(
            connection
        )
    app = create_app(ManagementConfig(management_database_url, environment="test"))
    principal = Principal(identity.account_id, identity.owner_user_id)
    now = datetime.now(UTC)
    session = Session(uuid4(), principal.account_id, "digest", "csrf", now, now, None)
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    with psycopg.connect(management_database_url, autocommit=True) as connection:
        before = _snapshot(connection)
        with TestClient(app) as client:
            listing = client.get("/api/v1/recommendations", params={"limit": 1})
            assert listing.status_code == 200, listing.text
            assert [item["id"] for item in listing.json()["items"]] == [str(rec.id)]
            detail = client.get(
                f"/api/v1/recommendations/{rec.id}",
                params={"assessment_revision_id": str(revision.id)},
            )
            assert detail.status_code == 200, detail.text
            assert detail.json()["assessment"]["id"] == str(revision.id)
            assert detail.json()["evidence_state"] == "unavailable"
            assert detail.json()["current_eligibility"] == "unavailable"
            history = client.get(f"/api/v1/recommendations/{rec.id}/assessments")
            assert history.status_code == 200, history.text
            assert [item["id"] for item in history.json()] == [str(revision.id)]
            for path in (
                f"recommendations/{foreign_rec.id}",
                f"recommendations/{rec.id}?assessment_revision_id={foreign_revision.id}",
                f"recommendations/{foreign_rec.id}/assessments",
                f"prospects/{uuid4()}",
            ):
                response = client.get(f"/api/v1/{path}")
                assert response.status_code == 404, response.text
                assert response.headers["cache-control"] == "no-store"
                assert response.headers["vary"] == "Cookie"
            for path in ("prospects", "suppressions"):
                response = client.get(f"/api/v1/{path}")
                assert response.status_code == 200, response.text
                assert response.json()["items"] == []
        assert _snapshot(connection) == before


def test_http_save_replays_exact_origin_without_partial_or_foreign_writes(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity, rec, revision = seed_owned_recommendation_revision(connection)
        foreign_identity, foreign_rec, foreign_revision = (
            seed_owned_recommendation_revision(connection)
        )
    app = create_app(ManagementConfig(management_database_url, environment="test"))
    principal = Principal(identity.account_id, identity.owner_user_id)
    now = datetime.now(UTC)
    session = Session(
        uuid4(), principal.account_id, "digest", digest_token("csrf"), now, now, None
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    body = {"assessment_revision_id": str(revision.id), "request_key": str(uuid4())}
    with TestClient(app) as client:
        assert (
            client.post(f"/api/v1/recommendations/{rec.id}/save", json=body).status_code
            == 403
        )
        response = client.post(
            f"/api/v1/recommendations/{rec.id}/save",
            json=body,
            headers={"X-CSRF-Token": "csrf"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["assessment_revision_id"] == str(revision.id)
        assert response.json()["prospect_stage"] == "saved"
        replay = client.post(
            f"/api/v1/recommendations/{rec.id}/save",
            json=body,
            headers={"X-CSRF-Token": "csrf"},
        )
        assert replay.json() == response.json()
        foreign = client.post(
            f"/api/v1/recommendations/{foreign_rec.id}/save",
            json={
                "assessment_revision_id": str(foreign_revision.id),
                "request_key": str(uuid4()),
            },
            headers={"X-CSRF-Token": "csrf"},
        )
        assert foreign.status_code == 404
        forbidden = client.post(
            f"/api/v1/recommendations/{rec.id}/save",
            json={**body, "business_id": str(identity.business_id)},
            headers={"X-CSRF-Token": "csrf"},
        )
        assert forbidden.status_code == 422
        detail = client.get(f"/api/v1/prospects/{response.json()['prospect_id']}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["origins"][0]["assessment_revision_id"] == str(revision.id)
        assert len(detail.json()["activities"]) == 1
        prospect_id = response.json()["prospect_id"]
        command = {
            "expected_version": 1,
            "request_key": str(uuid4()),
            "occurred_at": now.isoformat(),
            "target_stage": "contacted",
        }
        moved = client.post(
            f"/api/v1/prospects/{prospect_id}/stage",
            json=command,
            headers={"X-CSRF-Token": "csrf"},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["prospect"]["stage"] == "contacted"
        assert moved.json()["activity"]["actor_user_id"] == str(principal.user_id)
        assert (
            client.post(
                f"/api/v1/prospects/{prospect_id}/stage",
                json=command,
                headers={"X-CSRF-Token": "csrf"},
            ).json()
            == moved.json()
        )
        stale = client.post(
            f"/api/v1/prospects/{prospect_id}/notes",
            json={
                "expected_version": 1,
                "replacement_notes": "Stale draft",
                "occurred_at": now.isoformat(),
                "request_key": str(uuid4()),
            },
            headers={"X-CSRF-Token": "csrf"},
        )
        assert stale.status_code == 409, stale.text
        corrected = client.post(
            f"/api/v1/prospects/{prospect_id}/activity-time-corrections",
            json={
                "expected_version": 2,
                "original_activity_id": moved.json()["activity"]["id"],
                "expected_correction_head_id": None,
                "replacement_occurred_at": "2026-10-01T12:00:00+00:00",
                "request_key": str(uuid4()),
            },
            headers={"X-CSRF-Token": "csrf"},
        )
        assert corrected.status_code == 200, corrected.text
        refreshed = client.get(f"/api/v1/prospects/{prospect_id}").json()
        activity = next(
            item
            for item in refreshed["activities"]
            if item["id"] == moved.json()["activity"]["id"]
        )
        assert activity["correction_head_id"] == corrected.json()["activity"]["id"]
        assert activity["correction_sequence"] == 1
        assert activity["effective_occurred_at"].startswith("2026-10-01T12:00:00")
        assert activity["occurred_at"] == moved.json()["activity"]["occurred_at"]
        assert refreshed["stage"] == "contacted"
        assert refreshed["version"] == 2
        assert refreshed["notes"] == ""
    with psycopg.connect(management_database_url) as connection:
        assert (
            connection.execute(
                "SELECT status FROM operational.recommendations WHERE id=%s", (rec.id,)
            ).fetchone()[0]
            == "converted"
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.prospect_origins WHERE business_id=%s",
                (identity.business_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.prospect_activities WHERE business_id=%s",
                (identity.business_id,),
            ).fetchone()[0]
            == 3
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.prospects WHERE business_id=%s",
                (foreign_identity.business_id,),
            ).fetchone()[0]
            == 0
        )


def test_http_pause_replacement_reversal_and_feedback_preserve_history(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity, rec, revision = seed_owned_recommendation_revision(connection)
    now = datetime.now(UTC)
    app = create_app(
        ManagementConfig(management_database_url, environment="test"), clock=lambda: now
    )
    principal = Principal(identity.account_id, identity.owner_user_id)
    session = Session(
        uuid4(), principal.account_id, "digest", digest_token("csrf"), now, now, None
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    with TestClient(app) as client:

        def post(path, body):
            response = client.post(
                f"/api/v1/{path}", json=body, headers={"X-CSRF-Token": "csrf"}
            )
            assert response.status_code in (200, 201), response.text
            assert response.headers["cache-control"] == "no-store"
            return response.json()

        original_preference = client.get(
            "/api/v1/me/business/recommendation-preferences"
        )
        assert original_preference.status_code == 200, original_preference.text
        changed_preference = client.patch(
            "/api/v1/me/business/recommendation-preferences",
            json={
                "repeat_interval_days": original_preference.json()[
                    "repeat_interval_days"
                ]
                + 15
            },
            headers={"X-CSRF-Token": "csrf"},
        )
        assert changed_preference.status_code == 200, changed_preference.text
        preference = changed_preference.json()
        assert preference["business_id"] == str(identity.business_id)
        assert preference["repeat_interval_days"] == 45
        assert (
            client.get("/api/v1/me/business/recommendation-preferences").json()
            == preference
        )
        now = datetime.fromisoformat(preference["updated_at"]) + timedelta(seconds=1)
        later_body = {
            "assessment_revision_id": str(revision.id),
            "request_key": str(uuid4()),
            "expected_recommendation_version": rec.version,
            "pause_choice": "x2",
            "expected_repeat_interval_days": preference["repeat_interval_days"],
            "expected_preference_updated_at": preference["updated_at"],
            "expected_pause_id": None,
            "expected_pause_version": None,
        }
        first = post(f"recommendations/{rec.id}/later", later_body)
        assert datetime.fromisoformat(first["expires_at"]) == now + timedelta(
            days=2 * preference["repeat_interval_days"]
        )
        assert post(f"recommendations/{rec.id}/later", later_body) == first
        dismissed = client.get(
            "/api/v1/recommendations",
            params={
                "status": "dismissed",
                "strategy_id": str(revision.strategy_assessments[0].strategy_id),
            },
        )
        assert dismissed.status_code == 200, dismissed.text
        [muted] = dismissed.json()["items"]
        assert muted["id"] == str(rec.id)
        assert muted["status"] == "open"
        assert "paused" in muted["selection_blockers"]
        for status in ("open", "all", "rejected"):
            assert (
                client.get("/api/v1/recommendations", params={"status": status}).json()[
                    "items"
                ]
                == []
            )
        paused_at = now
        now = datetime.fromisoformat(first["expires_at"])
        assert (
            client.get(
                "/api/v1/recommendations", params={"status": "dismissed"}
            ).json()["items"]
            == []
        )
        now = paused_at
        blocked = client.get("/api/v1/suppressions").json()["items"][0]
        active = next(
            block
            for block in blocked["active_blocks"]
            if block["id"] == first["suppression_block_id"]
        )
        replacement_body = {
            **later_body,
            "request_key": str(uuid4()),
            "expected_recommendation_version": first["recommendation_version"],
            "pause_choice": "indefinite",
            "expected_pause_id": active["id"],
            "expected_pause_version": active["version"],
        }
        replacement = post(f"recommendations/{rec.id}/later", replacement_body)
        assert replacement["replaced_pause_id"] == first["suppression_block_id"]
        assert replacement["expires_at"] is None
        assert post(f"recommendations/{rec.id}/later", later_body) == first
        post(
            f"suppressions/{replacement['suppression_block_id']}/cancel-pause",
            {"expected_version": 1, "request_key": str(uuid4())},
        )
        assert (
            client.get(
                "/api/v1/recommendations", params={"status": "dismissed"}
            ).json()["items"]
            == []
        )
        rejected = post(
            f"recommendations/{rec.id}/not-relevant",
            {
                "assessment_revision_id": str(revision.id),
                "expected_recommendation_version": replacement[
                    "recommendation_version"
                ],
                "request_key": str(uuid4()),
                "reason": "Not our buyer",
            },
        )
        post(
            f"suppressions/{rejected['suppression_block_id']}/reverse-rejection",
            {"expected_version": 1, "request_key": str(uuid4())},
        )
        assert [
            item["id"]
            for item in client.get(
                "/api/v1/recommendations", params={"status": "dismissed"}
            ).json()["items"]
        ] == [str(rec.id)]
        feedback_body = {
            "assessment_revision_id": str(revision.id),
            "request_key": str(uuid4()),
            "feedback": {"usefulness": "useful", "next_step": "save", "outcome": "won"},
        }
        report = post(f"recommendations/{rec.id}/feedback", feedback_body)
        assert report["assessment_revision_id"] == str(revision.id)
        assert post(f"recommendations/{rec.id}/feedback", feedback_body) == report
        assert client.get("/api/v1/recommendations").json()["items"] == []
        assert client.get("/api/v1/prospects").json()["items"] == []
        assert (
            client.get(f"/api/v1/recommendations/{rec.id}").json()["status"]
            == "rejected"
        )
    with psycopg.connect(management_database_url) as connection:
        rows = connection.execute(
            "SELECT id,kind,cleared_at FROM operational.suppression_blocks WHERE business_id=%s",
            (identity.business_id,),
        ).fetchall()
        assert len(rows) == 3
        assert all(row[2] is not None for row in rows)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.recommendation_assessment_feedback WHERE business_id=%s",
                (identity.business_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.assessment_revisions WHERE business_id=%s",
                (identity.business_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.offer_cycles WHERE business_id=%s",
                (identity.business_id,),
            ).fetchone()[0]
            == 0
        )

from concurrent.futures import ThreadPoolExecutor

import psycopg
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from tests.management.test_matches_read_router import SESSION_TOKEN, FakeAuthentication
from tests.management.test_weekly_digest_repository import _subscriber


def test_icp_api_rejects_overlapping_create_and_merged_partial_patch(
    management_database_url,
):
    with psycopg.connect(management_database_url) as conn:
        user, _, strategy = _subscriber(conn, "icp-conflicts")
        profile = conn.execute(
            "SELECT ideal_client_profile_id FROM operational.client_discovery_strategies WHERE id=%s",
            (strategy,),
        ).fetchone()[0]
    app = create_app(
        ManagementConfig(management_database_url, environment="test"),
        authentication_service=FakeAuthentication(user),
    )
    with TestClient(app) as client:
        client.cookies.set("huginn_management_session", SESSION_TOKEN)
        headers = {"X-CSRF-Token": "csrf"}
        base = "/api/v1/ideal-client-profiles"
        invalid = {
            "name": "Conflict",
            "industries": [{"name": "Analytics"}],
            "exclusions": [{"kind": "industry", "name": " analytics "}],
        }
        assert client.post(base, json=invalid, headers=headers).status_code == 422
        url = f"{base}/{profile}"
        assert (
            client.patch(
                url,
                json={
                    "industries": [{"name": "Analytics"}],
                    "geographies": [{"kind": "country", "value": "USA"}],
                },
                headers=headers,
            ).status_code
            == 200
        )
        for exclusions in (
            [{"kind": "industry", "name": "analytics"}],
            [
                {
                    "kind": "geography",
                    "geography": {"kind": "country", "value": "United States"},
                }
            ],
        ):
            response = client.patch(
                url, json={"exclusions": exclusions}, headers=headers
            )
            assert response.status_code == 422
            assert response.json()["error"]["message"] == "Request validation failed"
            assert client.get(url).json()["exclusions"] == []
        assert (
            client.patch(
                url,
                json={
                    "industries": [],
                    "exclusions": [{"kind": "industry", "name": "Analytics"}],
                },
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            client.patch(
                url, json={"industries": [{"name": "Analytics"}]}, headers=headers
            ).status_code
            == 422
        )
        assert client.get(url).json()["industries"] == []


def test_concurrent_partial_patches_cannot_commit_a_selection_exclusion_conflict(
    management_database_url,
):
    with psycopg.connect(management_database_url) as conn:
        user, _, strategy = _subscriber(conn, "icp-concurrent-conflicts")
        profile = conn.execute(
            "SELECT ideal_client_profile_id FROM operational.client_discovery_strategies WHERE id=%s",
            (strategy,),
        ).fetchone()[0]
    app = create_app(
        ManagementConfig(management_database_url, environment="test"),
        authentication_service=FakeAuthentication(user),
    )

    def patch(body):
        with TestClient(app) as client:
            client.cookies.set("huginn_management_session", SESSION_TOKEN)
            return client.patch(
                f"/api/v1/ideal-client-profiles/{profile}",
                json=body,
                headers={"X-CSRF-Token": "csrf"},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                patch,
                (
                    {"industries": [{"name": "Analytics"}]},
                    {"exclusions": [{"kind": "industry", "name": "Analytics"}]},
                ),
            )
        )
    assert sorted(results) == [200, 422]

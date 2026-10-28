"""Shared filtering, multi-offering weekly selection, delivery and immutable history."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.application.services.recommendations import RecommendationService
from huginn.management.application.services.weekly_digest import WeeklyDigestService
from huginn.management.config import ManagementConfig
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.repositories.recommendations import (
    PostgresRecommendationRepository,
)
from huginn.management.persistence.repositories.weekly_digest import (
    PostgresWeeklyDigestRepository,
)
from tests.management.test_matches_read_router import SESSION_TOKEN, FakeAuthentication
from tests.management.test_weekly_digest_repository import _subscriber
from tests.matchmaking.test_evidence_integration import _reconcile, _seed_company
from tests.postgres_harness import provisioned_postgres


@pytest.fixture
def weekly_matching_database_url():
    with provisioned_postgres("weekly_matching_integration") as url:
        yield url


def test_seven_weekly_matches_use_shared_icp_rules_and_keep_exact_email_selection(
    weekly_matching_database_url,
):
    management_database_url = weekly_matching_database_url
    now = datetime.now(UTC)
    with psycopg.connect(management_database_url) as conn:
        conn.execute(Path("db/schema/operational-recommendations.sql").read_text())
        conn.execute(Path("db/schema/operational-weekly-digest.sql").read_text())
        user, _, first = _subscriber(conn, "weekly-integration")
        conn.execute(
            "UPDATE operational.service_offerings SET name='Directory research',description='Understand directory records' WHERE user_id=%s",
            (user,),
        )
        conn.execute(
            'UPDATE operational.ideal_client_profiles SET industries=\'[{"name":"SaaS"}]\',company_sizes=\'[{"band":"0-10"}]\',geographies=\'[{"kind":"country","value":"Germany"}]\' WHERE user_id=%s',
            (user,),
        )
        second_offering = conn.execute(
            "INSERT INTO operational.service_offerings(user_id,name,description) VALUES (%s,'Record research','Review directory records') RETURNING id",
            (user,),
        ).fetchone()[0]
        second_icp = conn.execute(
            'INSERT INTO operational.ideal_client_profiles(user_id,name,industries,company_sizes,geographies) VALUES (%s,\'UK targets\',\'[{"name":"SaaS"}]\',\'[{"band":"0-10"}]\',\'[{"kind":"country","value":"UK"}]\') RETURNING id',
            (user,),
        ).fetchone()[0]
        second = conn.execute(
            "INSERT INTO operational.client_discovery_strategies(user_id,name,service_offering_id,ideal_client_profile_id,is_active) VALUES (%s,'UK strategy',%s,%s,true) RETURNING id",
            (user, second_offering, second_icp),
        ).fetchone()[0]
        companies = []
        for country in ("DE", "DE", "DE", "UK", "UK", "UK", None, "US"):
            company, _ = _seed_company(conn, event_at=now - timedelta(days=1))
            conn.execute(
                "UPDATE gold.company SET country=%s WHERE id=%s", (country, company)
            )
            companies.append(company)
        legacy = conn.execute(
            "INSERT INTO operational.match(user_id,company_id,status,notes) VALUES (%s,%s,'contacted','Keep original notes') RETURNING id",
            (user, companies[-1]),
        ).fetchone()[0]
        conn.commit()
    _reconcile(management_database_url)

    def clock():
        return datetime.now(UTC) + timedelta(seconds=1)

    factory = ManagementConnectionFactory(management_database_url)

    def make_work():
        return UnitOfWork(factory)

    recommendations = RecommendationService(
        make_work,
        repository_factory=lambda work: PostgresRecommendationRepository(
            work.connection
        ),
        clock=clock,
    )
    direct = recommendations.generate(user, first)
    assert {UUID(item["company"]["id"]) for item in direct["items"]} == set(
        companies[:3] + companies[6:7]
    )
    messages = []

    class Sender:
        def send(self, message):
            messages.append(message)

    with make_work() as work:
        PostgresWeeklyDigestRepository(work.connection).subscribe(user, clock())
        work.commit()
    digest = WeeklyDigestService(
        make_work,
        repository_factory=lambda work: PostgresWeeklyDigestRepository(work.connection),
        recommendations=recommendations,
        sender=Sender(),
        web_origin="https://huginn.example",
        sender_address="weekly@huginn.example",
        signing_key="test-key",
        clock=clock,
    )
    assert digest.run()["sent"] == 1
    assert len(messages) == 1
    weekly = recommendations.weekly(user)
    assert len(weekly) == 1 and len(weekly[0]["items"]) == 7
    batch = weekly[0]
    assert {UUID(item["company"]["id"]) for item in batch["items"]} == set(
        companies[:7]
    )
    assert {entry["id"] for item in batch["items"] for entry in item["strategies"]} == {
        str(first),
        str(second),
    }
    unknown = next(
        item for item in batch["items"] if item["company"]["country"] is None
    )
    assert unknown["icp_fit"]["country"] == "unknown"
    assert "country is unverified" in " ".join(unknown["unknowns"])
    assert f"batch={batch['id']}" in messages[0].body
    assert "7. Evidence fixture" in messages[0].body
    recommendations.generate(user, second)
    assert recommendations.weekly(user)[0] == batch
    assert recommendations.latest(user, first)["id"] == direct["id"]
    assert digest.run()["skipped"] == 1 and len(messages) == 1
    app = create_app(
        ManagementConfig(management_database_url, environment="test"),
        authentication_service=FakeAuthentication(user),
    )
    with TestClient(app) as client:
        client.cookies.set("huginn_management_session", SESSION_TOKEN)
        response = client.get("/api/v1/recommendations/weekly")
        assert response.status_code == 200 and response.json()[0]["id"] == batch["id"]
        assert len(response.json()[0]["items"]) == 7
    with psycopg.connect(management_database_url) as conn:
        conn.execute(
            "UPDATE operational.client_discovery_strategies SET is_active=false WHERE user_id=%s",
            (user,),
        )
        assert conn.execute(
            "SELECT status,notes FROM operational.match WHERE id=%s", (legacy,)
        ).fetchone() == ("contacted", "Keep original notes")
    assert recommendations.weekly(user)[0] == batch

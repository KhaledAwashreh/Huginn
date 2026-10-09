"""Live read-only collected definition choices on disposable PostgreSQL16."""

from types import SimpleNamespace
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.value_objects.common import Principal
from huginn.management.presentation.api.dependencies.authentication import (
    get_authenticated_session,
)


def test_collected_options_keep_exact_values_and_company_search_is_bounded(
    management_database_url,
):
    ids = [uuid4() for _ in range(3)]
    app = create_app(ManagementConfig(management_database_url, environment="test"))
    client = TestClient(app)
    assert client.get("/api/v1/configuration-options").status_code == 401
    assert client.get("/api/v1/configuration-options/companies").status_code == 401
    app.dependency_overrides[get_authenticated_session] = lambda: SimpleNamespace(
        principal=Principal(uuid4(), uuid4())
    )
    try:
        with psycopg.connect(management_database_url) as connection:
            for company_id, name, country, sectors in [
                (ids[0], "Catalogue A 100%", "USA", ["B2B", "B2B", "Unspecified", ""]),
                (ids[1], "Catalogue B", "United States", ["B2B", "Healthcare"]),
                (ids[2], "Catalogue C", None, None),
            ]:
                connection.execute(
                    "INSERT INTO gold.company(id,domain,name,country,business_sector,company_scale) VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        company_id,
                        f"catalogue-{company_id}.test",
                        name,
                        country,
                        sectors,
                        "11-100",
                    ),
                )
        options = client.get("/api/v1/configuration-options")
        assert options.status_code == 200
        assert options.headers["Cache-Control"] == "no-store"
        values = options.json()
        industries = {
            item["value"]: item["company_count"] for item in values["industries"]
        }
        assert industries["B2B"] == 2
        assert "Unspecified" not in industries and "" not in industries
        assert {item["value"] for item in values["countries"]} >= {
            "USA",
            "United States",
        }
        first = client.get(
            "/api/v1/configuration-options/companies",
            params={"search": "Catalogue", "limit": 2},
        ).json()
        assert len(first["items"]) == 2 and first["has_more"]
        next_page = client.get(
            "/api/v1/configuration-options/companies",
            params={"search": "Catalogue", "limit": 2, "offset": 2},
        ).json()
        assert len(next_page["items"]) == 1 and not next_page["has_more"]
        literal = client.get(
            "/api/v1/configuration-options/companies", params={"search": "100%"}
        ).json()
        assert [item["id"] for item in literal["items"]] == [str(ids[0])]
        assert (
            client.get(f"/api/v1/configuration-options/companies/{ids[0]}").json()[
                "name"
            ]
            == "Catalogue A 100%"
        )
        assert (
            client.get(f"/api/v1/configuration-options/companies/{uuid4()}").status_code
            == 404
        )
        assert (
            client.get("/api/v1/configuration-options/companies?limit=101").status_code
            == 422
        )
        with psycopg.connect(management_database_url) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM gold.company WHERE id=ANY(%s)", (ids,)
                ).fetchone()[0]
                == 3
            )
    finally:
        with psycopg.connect(management_database_url) as connection:
            connection.execute("DELETE FROM gold.company WHERE id=ANY(%s)", (ids,))

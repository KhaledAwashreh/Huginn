"""Real TLS proxy, Uvicorn, authentication and disposable PostgreSQL integration."""

import json
from uuid import uuid4

import psycopg
from fastapi import Request

from huginn.management.app import create_account_administration_services, create_app
from huginn.management.application.commands.provisioning import ProvisionIdentity
from huginn.management.config import ManagementConfig
from tests.https_proxy_harness import real_https_proxy


def test_actual_https_ingress_authentication_and_forwarded_identity(
    management_database_url,
    tmp_path,
):
    username = f"https-{uuid4()}"
    password = "disposable-https-only-password"
    config = ManagementConfig(management_database_url, environment="production")
    identity = create_account_administration_services(config).provisioning.provision(
        ProvisionIdentity(
            username=username,
            first_name="HTTPS",
            last_name="Test",
            email=f"{username}@example.test",
            phone_number="+12025550123",
            country_of_residence="US",
            timezone="UTC",
            password=password,
        )
    )
    app = create_app(config)

    @app.get("/__test_identity")
    def request_identity(request: Request):
        return {"scheme": request.url.scheme, "client": request.client.host}

    with real_https_proxy(app, tmp_path / "proxy") as proxy:
        assert proxy.request("/ready")[0] == 200
        spoofed = proxy.request(
            "/__test_identity",
            headers={
                "X-Forwarded-For": "203.0.113.42",
                "X-Forwarded-Proto": "http",
                "Forwarded": "for=203.0.113.42;proto=http",
            },
        )
        assert json.loads(spoofed[2]) == {"scheme": "https", "client": "127.0.0.1"}
        same_origin = {"Origin": proxy.origin, "Sec-Fetch-Site": "same-origin"}
        login = proxy.request(
            "/api/v1/sessions",
            method="POST",
            headers=same_origin,
            data={"username": username, "password": password},
        )
        assert login[0] == 200
        assert "Secure" in login[1]["set-cookie"]
        assert "HttpOnly" in login[1]["set-cookie"]
        csrf = json.loads(login[2])["csrf_token"]
        assert proxy.request("/api/v1/sessions/current")[0] == 200
        mutation_headers = {**same_origin, "X-CSRF-Token": csrf}
        changed = proxy.request(
            "/api/v1/me",
            method="PATCH",
            headers=mutation_headers,
            data={"first_name": "Verified HTTPS"},
        )
        assert changed[0] == 200
        with psycopg.connect(management_database_url) as conn:
            assert conn.execute(
                "SELECT first_name FROM operational.users WHERE id=%s",
                (identity.user_id,),
            ).fetchone() == ("Verified HTTPS",)
        assert (
            proxy.request(
                "/api/v1/me",
                method="PATCH",
                headers=mutation_headers,
                data={"first_name": "HTTPS"},
            )[0]
            == 200
        )
        hostile = {
            **mutation_headers,
            "Origin": "https://evil.example",
            "X-Forwarded-Host": "localhost",
            "X-Forwarded-Proto": "https",
        }
        assert (
            proxy.request(
                "/api/v1/sessions",
                method="POST",
                headers=hostile,
                data={"username": username, "password": password},
            )[0]
            == 403
        )
        assert (
            proxy.request(
                "/api/v1/sessions/current", method="DELETE", headers=hostile, data={}
            )[0]
            == 403
        )
        assert (
            proxy.request(
                "/api/v1/sessions/current",
                method="DELETE",
                headers=mutation_headers,
                data={},
            )[0]
            == 204
        )
        assert proxy.request("/api/v1/sessions/current")[0] == 401
        assert proxy.request("/health", host="unknown.localhost", https=False)[0] == 404
        challenge = proxy.request(
            "/.well-known/acme-challenge/unknown-token", https=False
        )
        assert challenge[0] == 404
        assert "location" not in challenge[1]
        redirected = proxy.request("/path?query=value", https=False)
        assert redirected[0] in {301, 308}
        assert redirected[1]["location"] == "https://localhost/path?query=value"
        posted = proxy.request("/path?query=value", method="POST", https=False, data={})
        assert posted[0] == 308
        alias = proxy.request("/path?query=value", host="alias.localhost")
        assert alias[0] in {301, 308}
        assert alias[1]["location"] == "https://localhost/path?query=value"
        storage = proxy.directory / "state/acme.json"
        stored_certificate = storage.read_bytes()
        assert storage.stat().st_mode & 0o777 == 0o600
        proxy.recreate()
        assert proxy.request("/ready")[0] == 200
        assert storage.read_bytes() == stored_certificate

"""Disposable real-API browser fixture; never uses a configured/shared database."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import uvicorn

from huginn.management.app import create_account_administration_services, create_app
from huginn.management.application.commands.provisioning import ProvisionIdentity
from huginn.management.config import ManagementConfig
from huginn.management.security.tokens import digest_token
from tests.browser_lifecycle_mail import browser_lifecycle_mail
from tests.postgres_harness import provisioned_postgres

PASSWORD = "browser-only-correct-horse-battery"
LEGACY_TOKEN = "legacy-browser-only-" + "a" * 64
LEGACY_PROOF = "legacy-browser-proof-" + "b" * 64


def main() -> None:
    name = f"huginn_browser_{uuid4().hex}"
    with provisioned_postgres(name) as database_url:
        config = ManagementConfig(database_url, environment="test")
        provisioning = create_account_administration_services(config).provisioning
        identities = {}
        for username in ("browser-ada", "browser-bob", "browser-legacy"):
            identities[username] = provisioning.provision(
                ProvisionIdentity(
                    username=username,
                    first_name="Ada" if username == "browser-ada" else "Bob",
                    last_name="Browser",
                    email=f"{username}@example.test",
                    phone_number="+12025550123",
                    country_of_residence="US",
                    timezone="UTC",
                    password=PASSWORD,
                )
            )
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "INSERT INTO operational.sessions "
                "(account_id, token_digest, csrf_digest, expires_at) VALUES (%s,%s,%s,%s)",
                (
                    identities["browser-legacy"].account_id,
                    digest_token(LEGACY_TOKEN),
                    digest_token(LEGACY_PROOF),
                    datetime.now(UTC) + timedelta(hours=1),
                ),
            )
        with browser_lifecycle_mail(config) as lifecycle_config:
            uvicorn.run(
                create_app(lifecycle_config),
                host="127.0.0.1",
                port=8000,
                log_level="warning",
            )


if __name__ == "__main__":
    main()

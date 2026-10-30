"""Run the explicit admin data migration with private deployment credentials."""

import json
import logging
import os
from pathlib import Path

import psycopg

from huginn.management.domain.services.identity_validation import normalized_email
from huginn.management.security.passwords import hash_password, validate_new_password

logger = logging.getLogger(__name__)


def main(*, database_url: str | None = None) -> int:
    try:
        configurations = []
        for prefix in ("HUGINN_BOOTSTRAP_ADMIN", "HUGINN_BOOTSTRAP_SECOND_ADMIN"):
            username = os.environ[f"{prefix}_USERNAME"].strip()
            if not username:
                raise ValueError("admin username is required")
            password = validate_new_password(os.environ[f"{prefix}_PASSWORD"])
            configurations.append(
                {
                    "username": username,
                    "email": normalized_email(os.environ[f"{prefix}_EMAIL"]),
                    "password_hash": hash_password(password),
                    "first_name": username,
                    "last_name": "Founder",
                    "headline": "Huginn co-founder",
                }
            )
        if len({value["username"].casefold() for value in configurations}) != 2:
            raise ValueError("founder usernames must be distinct")
        if len({value["email"] for value in configurations}) != 2:
            raise ValueError("founder emails must be distinct")
        migration = (
            Path(__file__).resolve().parents[1]
            / "db/schema/operational-bootstrap-admin.sql"
        )
        with psycopg.connect(
            database_url
            if database_url is not None
            else os.environ["HUGINN_MANAGEMENT_DATABASE_URL"],
            options="-c statement_timeout=15000 -c lock_timeout=5000",
        ) as conn:
            statement = migration.read_text()
            for configuration in configurations:
                conn.execute(
                    "SELECT set_config('huginn.bootstrap_admin', %s, true)",
                    (json.dumps(configuration),),
                )
                conn.execute(statement)
        logger.info("Founder admin migration completed; existing credentials preserved")
        return 0
    except Exception as exc:
        logger.error(
            "Admin seed failed; check configuration and account conflicts (%s)",
            type(exc).__name__,
        )
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())

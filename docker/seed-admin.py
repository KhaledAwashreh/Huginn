"""Run the explicit admin data migration with private deployment credentials."""

import json
import logging
import os
from pathlib import Path

import psycopg

from huginn.management.domain.services.identity_validation import normalized_email
from huginn.management.security.passwords import hash_password, validate_new_password

logger = logging.getLogger(__name__)


def main() -> int:
    try:
        username = os.environ["HUGINN_BOOTSTRAP_ADMIN_USERNAME"].strip()
        if not username:
            raise ValueError("admin username is required")
        password = validate_new_password(os.environ["HUGINN_BOOTSTRAP_ADMIN_PASSWORD"])
        configuration = {
            "username": username,
            "email": normalized_email(os.environ["HUGINN_BOOTSTRAP_ADMIN_EMAIL"]),
            "password_hash": hash_password(password),
        }
        migration = (
            Path(__file__).resolve().parents[1]
            / "db/schema/operational-bootstrap-admin.sql"
        )
        with psycopg.connect(
            os.environ["HUGINN_MANAGEMENT_DATABASE_URL"],
            options="-c statement_timeout=15000 -c lock_timeout=5000",
        ) as conn:
            conn.execute(
                "SELECT set_config('huginn.bootstrap_admin', %s, true)",
                (json.dumps(configuration),),
            )
            conn.execute(migration.read_text())
        logger.info(
            "Bootstrap admin migration completed; existing credentials preserved"
        )
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

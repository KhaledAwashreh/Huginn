"""Management database adapters defined by ADR-0011."""

import logging

import psycopg

logger = logging.getLogger(__name__)

_PROBES = (
    "SELECT 1",
    "SELECT id, username, password_hash, status, created_at, updated_at "
    "FROM operational.accounts LIMIT 0",
    "SELECT id, account_id, first_name, last_name, email, phone_number, "
    "country_of_residence, timezone, created_at, updated_at "
    "FROM operational.users LIMIT 0",
    "SELECT id, user_id, headline, professional_summary, skills, experience, "
    "previous_projects, created_at, updated_at "
    "FROM operational.professional_profiles LIMIT 0",
)


class PostgresReadiness:
    """Read-only Postgres readiness adapter defined by ADR-0011."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def is_ready(self) -> bool:
        try:
            with psycopg.connect(
                self._database_url,
                connect_timeout=2,
                options=(
                    "-c statement_timeout=2000 -c default_transaction_read_only=on"
                ),
            ) as conn:
                for query in _PROBES:
                    conn.execute(query)
            return True
        except psycopg.Error as exc:
            logger.warning("Management readiness failed: %s", type(exc).__name__)
            return False

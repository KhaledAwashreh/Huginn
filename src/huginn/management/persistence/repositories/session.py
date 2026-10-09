"""PostgreSQL opaque session repository."""

from datetime import datetime
from typing import Any
from uuid import UUID

from huginn.management.domain.entities.session import Session
from huginn.management.domain.value_objects.account_role import AccountRole
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.session import NewSession
from huginn.management.persistence.contracts.repositories.session import (
    SessionRepository,
)
from huginn.management.persistence.repositories.common import PostgresIdentityRepository


class PostgresSessionRepository(PostgresIdentityRepository, SessionRepository):
    """Digest-only session persistence on the caller's transaction."""

    _columns = (
        "id, account_id, token_digest, csrf_digest, created_at, expires_at, revoked_at"
    )

    @staticmethod
    def _map(row: tuple[Any, ...]) -> Session:
        return Session(*row)

    def create(self, session: NewSession) -> Session:
        return self._map(
            self._write(
                "INSERT INTO operational.sessions "
                "(account_id, token_digest, csrf_digest, expires_at) "
                f"VALUES (%s, %s, %s, %s) RETURNING {self._columns}",
                (
                    session.account_id,
                    session.token_digest,
                    session.csrf_digest,
                    session.expires_at,
                ),
            )
        )

    def get_by_token_digest(self, token_digest: str) -> Session | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.sessions WHERE token_digest = %s",
            (token_digest,),
        )
        return self._map(row) if row else None

    def get_active_principal_by_token_digest(
        self, token_digest: str, now: datetime
    ) -> Principal | None:
        row = self._one(
            "SELECT a.id, u.id, a.role FROM operational.sessions s "
            "JOIN operational.accounts a ON a.id = s.account_id "
            "JOIN operational.users u ON u.account_id = a.id "
            "WHERE s.token_digest = %s AND s.revoked_at IS NULL "
            "AND s.expires_at > %s AND a.status = 'active'",
            (token_digest, now),
        )
        return Principal(row[0], row[1], AccountRole(row[2])) if row else None

    def initialize_csrf_digest(
        self,
        session_id: UUID,
        token_digest: str,
        principal: Principal,
        expected_digest: str,
        csrf_digest: str,
        now: datetime,
    ) -> Session | None:
        # Lock in the same account-before-session order as password changes and
        # administrator revocation. Waiting callers recheck disabled state.
        account = self._one(
            "SELECT a.id FROM operational.accounts a "
            "JOIN operational.users u ON u.account_id = a.id "
            "WHERE a.id = %s AND u.id = %s AND a.status = 'active' "
            "FOR UPDATE OF a",
            (principal.account_id, principal.user_id),
        )
        if account is None:
            return None
        # UPDATE evaluates WHERE before waiting for a tuple lock. Take the
        # session lock first so the subsequent expiry check uses the clock
        # after all lock waits, including a holder that changes no row values.
        locked_session = self._one(
            "SELECT id, csrf_digest FROM operational.sessions "
            "WHERE id = %s AND account_id = %s AND token_digest = %s FOR UPDATE",
            (session_id, principal.account_id, token_digest),
        )
        if locked_session is None:
            return None
        row = self._one(
            "UPDATE operational.sessions SET csrf_digest = %s "
            "WHERE id = %s AND account_id = %s AND token_digest = %s "
            "AND revoked_at IS NULL AND expires_at > GREATEST(%s, clock_timestamp()) "
            "AND (csrf_digest = %s OR csrf_digest = %s) "
            f"RETURNING {self._columns}",
            (
                csrf_digest,
                session_id,
                principal.account_id,
                token_digest,
                now,
                expected_digest,
                csrf_digest,
            ),
        )
        return self._map(row) if row else None

    def revoke_current(self, session_id: UUID, revoked_at: datetime) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE operational.sessions SET revoked_at = %s "
                "WHERE id = %s AND revoked_at IS NULL",
                (revoked_at, session_id),
            )

    def revoke_for_account(self, account_id: UUID, revoked_at: datetime) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE operational.sessions SET revoked_at = %s "
                "WHERE account_id = %s AND revoked_at IS NULL",
                (revoked_at, account_id),
            )

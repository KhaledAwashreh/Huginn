"""Authentication use cases and session-token coordination."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from huginn.management.constants.authentication import (
    GENERIC_AUTHENTICATION_FAILURE,
    PASSWORD_HASH_METHOD,
    SESSION_TTL_SECONDS,
)
from huginn.management.domain.common import Principal
from huginn.management.domain.session import (
    NewSession,
    Session,
)
from huginn.management.errors.domain import (
    AuthenticationError,
    ValidationDomainError,
)
from huginn.management.repositories.protocols.account import AccountRepository
from huginn.management.repositories.protocols.session import SessionRepository
from huginn.management.security.passwords import (
    Password,
    hash_password,
    needs_rehash,
    verify_password,
)
from huginn.management.security.tokens import digest_token, generate_token


@dataclass(frozen=True)
class IssuedSession:
    account_id: UUID
    session_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    """Principal and live session resolved from one repository snapshot."""

    principal: Principal
    session: Session


class _SessionOperations:
    """Digest-only session operations used by AuthenticationService."""

    def __init__(
        self,
        sessions: SessionRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        token_generator: Callable[[], str] | None = None,
        ttl: timedelta = timedelta(seconds=SESSION_TTL_SECONDS),
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("session TTL must be positive")
        self._sessions = sessions
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_generator = token_generator or generate_token
        self._ttl = ttl

    @staticmethod
    def digest(token: str) -> str:
        return digest_token(token)

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("session clock must return a timezone-aware datetime")
        return now.astimezone(UTC)

    def create(self, account_id: UUID) -> IssuedSession:
        token = self._token_generator()
        csrf = self._token_generator()
        expires_at = self._now() + self._ttl
        self._sessions.create(
            NewSession(account_id, self.digest(token), self.digest(csrf), expires_at)
        )
        return IssuedSession(account_id, token, csrf, expires_at)

    def resolve(self, token: str) -> Session | None:
        if not isinstance(token, str) or not token:
            return None
        session = self._sessions.get_by_token_digest(self.digest(token))
        if (
            session is None
            or session.revoked_at is not None
            or session.expires_at <= self._now()
        ):
            return None
        return session

    def revoke_current(self, token: str) -> None:
        session = self.resolve(token)
        if session is not None:
            self._sessions.revoke_current(session.id, self._now())

    def revoke_account(self, account_id: UUID) -> None:
        self._sessions.revoke_for_account(account_id, self._now())


class AuthenticationService:
    """Own login, token authentication, logout, password changes, and rehashing."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        config: Any,
        throttle: Any,
        *,
        accounts_factory: Callable[[Any], AccountRepository] | None = None,
        sessions_factory: Callable[[Any], SessionRepository] | None = None,
        clock: Callable[[], datetime] | None = None,
        token_generator: Callable[[], str] | None = None,
        verify_password_fn: Callable[[Password, str], bool] | None = None,
        hash_password_fn: Callable[[Password], str] | None = None,
        needs_rehash_fn: Callable[[str], bool] | None = None,
        password_method: str = PASSWORD_HASH_METHOD,
        dummy_password_hash: str | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._config = config
        self._throttle = throttle
        self._accounts_factory = accounts_factory
        self._sessions_factory = sessions_factory
        self._clock = clock
        self._token_generator = token_generator
        self._verify_password = verify_password_fn or verify_password
        self._hash_password = hash_password_fn
        self._password_method = password_method
        self._dummy_password_hash = dummy_password_hash or hash_password(
            Password(generate_token()), method=PASSWORD_HASH_METHOD
        )
        if password_method == "scrypt":
            canonical = self._dummy_password_hash.partition("$")[0]
        else:
            canonical = hash_password(
                Password(generate_token()), method=password_method
            ).partition("$")[0]
        self._needs_rehash = needs_rehash_fn or (
            lambda encoded: needs_rehash(encoded, canonical)
        )

    def _accounts(self, uow: Any) -> AccountRepository:
        if self._accounts_factory is None:
            raise RuntimeError("AuthenticationService requires an AccountRepository")
        return self._accounts_factory(uow)

    def _sessions(self, uow: Any) -> SessionRepository:
        if self._sessions_factory is None:
            raise RuntimeError("AuthenticationService requires a SessionRepository")
        return self._sessions_factory(uow)

    def _session_operations(self, sessions: SessionRepository) -> _SessionOperations:
        return _SessionOperations(
            sessions,
            clock=self._clock,
            token_generator=self._token_generator,
            ttl=getattr(
                self._config,
                "session_ttl",
                timedelta(seconds=SESSION_TTL_SECONDS),
            ),
        )

    def login(self, *, username: str, password: str, client_ip: str) -> IssuedSession:
        """Verify credentials and issue a new session in one unit of work."""
        reservation = self._throttle.reserve(client_ip, username)
        completed = False
        try:
            try:
                secret = Password(password)
            except (TypeError, ValueError) as exc:
                self._throttle.record_failure(client_ip, username, reservation)
                completed = True
                raise AuthenticationError(GENERIC_AUTHENTICATION_FAILURE) from exc

            with self._uow_factory() as uow:
                accounts = self._accounts(uow)
                account = accounts.get_by_normalized_username_for_update(username)
                encoded_hash = (
                    account.password_hash
                    if account is not None and account.status == "active"
                    else self._dummy_password_hash
                )
                verified = self._verify_password(secret, encoded_hash)
                if account is None or account.status != "active" or not verified:
                    self._throttle.record_failure(client_ip, username, reservation)
                    completed = True
                    raise AuthenticationError(GENERIC_AUTHENTICATION_FAILURE)

                if self._needs_rehash(account.password_hash):
                    updated = accounts.set_password_hash(
                        account.id, self._hasher()(secret)
                    )
                    if updated is None:
                        raise AuthenticationError(GENERIC_AUTHENTICATION_FAILURE)
                issued = self._session_operations(self._sessions(uow)).create(
                    account.id
                )
                uow.commit()
            self._throttle.record_success(client_ip, username, reservation)
            completed = True
            return issued
        finally:
            if not completed:
                self._throttle.release(reservation)

    def authenticate(self, token: str) -> Principal | None:
        """Resolve an active session token to its Account/User principal."""
        result = self.authenticate_session(token)
        return result.principal if result is not None else None

    def authenticate_session(self, token: str) -> AuthenticatedSession | None:
        """Resolve principal and session together for authentication dependencies."""
        now = self._now()
        with self._uow_factory() as uow:
            sessions = self._sessions(uow)
            lookup = getattr(sessions, "get_active_principal_by_token_digest", None)
            if lookup is None or not isinstance(token, str) or not token:
                return None
            token_digest = digest_token(token)
            session = sessions.get_by_token_digest(token_digest)
            principal = lookup(token_digest, now)
            if (
                session is None
                or principal is None
                or session.account_id != principal.account_id
            ):
                return None
            return AuthenticatedSession(principal, session)

    def logout(self, token: str) -> None:
        """Revoke the current active session in its own unit of work."""
        with self._uow_factory() as uow:
            self._session_operations(self._sessions(uow)).revoke_current(token)
            uow.commit()

    def change_password(
        self, account_id: UUID, *, current_password: str, new_password: str
    ) -> None:
        """Change a password and revoke all Account sessions atomically."""
        try:
            current = Password(current_password)
            new = Password(new_password)
        except (TypeError, ValueError) as exc:
            raise ValidationDomainError("invalid password") from exc

        with self._uow_factory() as uow:
            accounts = self._accounts(uow)
            account = accounts.get_by_id_for_update(account_id)
            if (
                account is None
                or account.status != "active"
                or not self._verify_password(current, account.password_hash)
            ):
                raise AuthenticationError("current password is incorrect")
            if accounts.set_password_hash(account.id, self._hasher()(new)) is None:
                raise AuthenticationError("current password is incorrect")
            self._session_operations(self._sessions(uow)).revoke_account(account.id)
            uow.commit()

    def _hasher(self) -> Callable[[Password], str]:
        return self._hash_password or (
            lambda value: hash_password(value, method=self._password_method)
        )

    def _now(self) -> datetime:
        now = self._clock() if self._clock is not None else datetime.now(UTC)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError(
                "authentication clock must return a timezone-aware datetime"
            )
        return now.astimezone(UTC)

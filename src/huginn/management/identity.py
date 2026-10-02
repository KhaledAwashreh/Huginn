"""Identity persistence and owner-controlled aggregate use cases."""

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError
from werkzeug.security import generate_password_hash

from huginn.management.domain import (
    Account,
    AuthenticationError,
    ConflictError,
    NewAccount,
    NewProfessionalProfile,
    NewSession,
    NewUser,
    NotFoundError,
    Principal,
    ProfessionalProfile,
    ProfessionalProfileChanges,
    Session,
    User,
    UserChanges,
    ValidationDomainError,
)
from huginn.management.passwords import Password
from huginn.management.primitives import (
    E164Phone,
    Email,
    IanaTimezone,
    NonBlankText,
    StrictModel,
)
from huginn.management.schemas import Experience, PreviousProject, Skill


class IdentityInput(StrictModel):
    username: NonBlankText
    first_name: NonBlankText
    last_name: NonBlankText
    email: Email
    phone_number: E164Phone
    country_of_residence: NonBlankText
    timezone: IanaTimezone | None = None


class PostgresIdentityRepository:
    """Base for resource-specific repositories bound to one UoW connection."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def _one(self, query: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def _write(self, query: str, params: tuple[Any, ...]) -> tuple[Any, ...]:
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        assert row is not None
        return row

    @staticmethod
    def _translate(exc: psycopg.IntegrityError) -> Exception:
        constraint = getattr(getattr(exc, "diag", None), "constraint_name", "") or ""
        if constraint == "accounts_username_lower_key":
            return ConflictError("username is already in use")
        return ValidationDomainError("identity data violates a database constraint")


class PostgresAccountRepository(PostgresIdentityRepository):
    _columns = "id, username, password_hash, status, created_at, updated_at"

    @staticmethod
    def _map(row: tuple[Any, ...]) -> Account:
        return Account(*row)

    def get_by_id(self, account_id: UUID) -> Account | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.accounts WHERE id = %s",
            (account_id,),
        )
        return self._map(row) if row else None

    def get_by_id_for_update(self, account_id: UUID) -> Account | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.accounts WHERE id = %s FOR UPDATE",
            (account_id,),
        )
        return self._map(row) if row else None

    def get_by_normalized_username(self, username: str) -> Account | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.accounts "
            "WHERE lower(username) = lower(%s)",
            (username.strip(),),
        )
        return self._map(row) if row else None

    def get_by_normalized_username_for_update(self, username: str) -> Account | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.accounts "
            "WHERE lower(username) = lower(%s) FOR UPDATE",
            (username.strip(),),
        )
        return self._map(row) if row else None

    def create(self, account: NewAccount) -> Account:
        try:
            row = self._write(
                f"INSERT INTO operational.accounts (username, password_hash, status) "
                f"VALUES (%s, %s, %s) RETURNING {self._columns}",
                (account.username.strip(), account.password_hash, account.status),
            )
            return self._map(row)
        except psycopg.IntegrityError as exc:
            raise self._translate(exc) from exc

    def set_status(self, account_id: UUID, status: str) -> Account | None:
        row = self._one(
            f"UPDATE operational.accounts SET status = %s, updated_at = clock_timestamp() "
            f"WHERE id = %s RETURNING {self._columns}",
            (status, account_id),
        )
        return self._map(row) if row else None

    def set_password_hash(self, account_id: UUID, password_hash: str) -> Account | None:
        row = self._one(
            f"UPDATE operational.accounts SET password_hash = %s, updated_at = clock_timestamp() "
            f"WHERE id = %s RETURNING {self._columns}",
            (password_hash, account_id),
        )
        return self._map(row) if row else None


class PostgresUserRepository(PostgresIdentityRepository):
    _columns = (
        "id, account_id, first_name, last_name, email, phone_number, "
        "country_of_residence, timezone, created_at, updated_at"
    )

    @staticmethod
    def _map(row: tuple[Any, ...]) -> User:
        return User(*row)

    def get_by_id(self, user_id: UUID) -> User | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.users WHERE id = %s",
            (user_id,),
        )
        return self._map(row) if row else None

    def get_by_account_id(self, account_id: UUID) -> User | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.users WHERE account_id = %s",
            (account_id,),
        )
        return self._map(row) if row else None

    def create(self, user: NewUser) -> User:
        try:
            row = self._write(
                f"INSERT INTO operational.users (account_id, first_name, last_name, email, "
                f"phone_number, country_of_residence, timezone) "
                f"VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING {self._columns}",
                (
                    user.account_id,
                    user.first_name,
                    user.last_name,
                    user.email,
                    user.phone_number,
                    user.country_of_residence,
                    user.timezone,
                ),
            )
            return self._map(row)
        except psycopg.IntegrityError as exc:
            raise self._translate(exc) from exc

    def update(self, user_id: UUID, changes: UserChanges) -> User | None:
        columns = {
            "first_name": "first_name",
            "last_name": "last_name",
            "email": "email",
            "phone_number": "phone_number",
            "country_of_residence": "country_of_residence",
            "timezone": "timezone",
        }
        supplied = changes.supplied_fields
        if not supplied:
            return self.get_by_id(user_id)
        if supplied - columns.keys():
            raise ValueError("unsupported User update field")
        fields = sorted(supplied)
        assignments = ", ".join(f"{columns[name]} = %s" for name in fields)
        parameters = tuple(changes.values[name] for name in fields)
        try:
            row = self._one(
                f"UPDATE operational.users SET {assignments}, updated_at = clock_timestamp() "
                f"WHERE id = %s RETURNING {self._columns}",
                (*parameters, user_id),
            )
        except psycopg.IntegrityError as exc:
            raise self._translate(exc) from exc
        return self._map(row) if row else None


class PostgresProfessionalProfileRepository(PostgresIdentityRepository):
    _columns = (
        "id, user_id, headline, professional_summary, skills, experience, "
        "previous_projects, created_at, updated_at"
    )

    @staticmethod
    def _map(row: tuple[Any, ...]) -> ProfessionalProfile:
        collections = (
            [Skill.model_validate(item).model_dump(mode="json") for item in row[4]],
            [
                Experience.model_validate(item).model_dump(mode="json")
                for item in row[5]
            ],
            [
                PreviousProject.model_validate(item).model_dump(mode="json")
                for item in row[6]
            ],
        )
        return ProfessionalProfile(
            row[0],
            row[1],
            row[2],
            row[3],
            tuple(collections[0]),
            tuple(collections[1]),
            tuple(collections[2]),
            row[7],
            row[8],
        )

    def get_owned(self, user_id: UUID) -> ProfessionalProfile | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.professional_profiles "
            "WHERE user_id = %s",
            (user_id,),
        )
        return self._map(row) if row else None

    def create(self, profile: NewProfessionalProfile) -> ProfessionalProfile:
        try:
            row = self._write(
                f"INSERT INTO operational.professional_profiles (user_id) VALUES (%s) "
                f"RETURNING {self._columns}",
                (profile.user_id,),
            )
            return self._map(row)
        except psycopg.IntegrityError as exc:
            raise self._translate(exc) from exc

    def update_owned(
        self, user_id: UUID, changes: ProfessionalProfileChanges
    ) -> ProfessionalProfile | None:
        columns = {
            "headline": "headline",
            "professional_summary": "professional_summary",
            "skills": "skills",
            "experience": "experience",
            "previous_projects": "previous_projects",
        }
        supplied = changes.supplied_fields
        if not supplied:
            return self.get_owned(user_id)
        if supplied - columns.keys():
            raise ValueError("unsupported ProfessionalProfile update field")
        fields = sorted(supplied)
        assignments = ", ".join(f"{columns[name]} = %s" for name in fields)
        parameters = tuple(
            Jsonb([dict(item) for item in changes.values[name]])
            if name in {"skills", "experience", "previous_projects"}
            else changes.values[name]
            for name in fields
        )
        try:
            row = self._one(
                f"UPDATE operational.professional_profiles SET {assignments}, "
                f"updated_at = clock_timestamp() WHERE user_id = %s RETURNING {self._columns}",
                (*parameters, user_id),
            )
        except psycopg.IntegrityError as exc:
            raise self._translate(exc) from exc
        return self._map(row) if row else None


class PostgresSessionRepository(PostgresIdentityRepository):
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
            "SELECT a.id, u.id FROM operational.sessions s "
            "JOIN operational.accounts a ON a.id = s.account_id "
            "JOIN operational.users u ON u.account_id = a.id "
            "WHERE s.token_digest = %s AND s.revoked_at IS NULL "
            "AND s.expires_at > %s AND a.status = 'active'",
            (token_digest, now),
        )
        return Principal(*row) if row else None

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


@dataclass(frozen=True)
class IssuedSession:
    account_id: UUID
    session_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_at: datetime


class SessionService:
    """Issue opaque tokens and resolve/revoke sessions through a repository."""

    def __init__(
        self,
        sessions: Any,
        *,
        clock: Callable[[], datetime] | None = None,
        token_generator: Callable[[], str] | None = None,
        ttl: timedelta = timedelta(hours=12),
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("session TTL must be positive")
        self._sessions = sessions
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_generator = token_generator or (lambda: secrets.token_urlsafe(32))
        self._ttl = ttl

    @staticmethod
    def digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

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

    def resolve_principal(self, token: str) -> Principal | None:
        if not isinstance(token, str) or not token:
            return None
        lookup = getattr(self._sessions, "get_active_principal_by_token_digest", None)
        if lookup is None:
            return None
        return lookup(self.digest(token), self._now())

    def revoke_current(self, token: str) -> None:
        session = self.resolve(token)
        if session is not None:
            self._sessions.revoke_current(session.id, self._now())

    def revoke_account(self, account_id: UUID) -> None:
        self._sessions.revoke_for_account(account_id, self._now())


def _password_hash_needs_rehash(encoded: str, canonical_method: str) -> bool:
    return encoded.partition("$")[0] != canonical_method


class LoginService:
    """Authenticate an Account and issue its session in one unit of work."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        config: Any,
        throttle: Any,
        *,
        accounts_factory: Callable[[Any], Any] | None = None,
        sessions_factory: Callable[[Any], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
        token_generator: Callable[[], str] | None = None,
        verify_password: Callable[[Password, str], bool] | None = None,
        hash_password: Callable[[Password], str] | None = None,
        needs_rehash: Callable[[str], bool] | None = None,
        password_method: str = "scrypt",
        dummy_password_hash: str | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._config = config
        self._throttle = throttle
        self._accounts_factory = accounts_factory
        self._sessions_factory = sessions_factory
        self._clock = clock
        self._token_generator = token_generator
        self._verify_password = verify_password
        self._hash_password = hash_password
        self._password_method = password_method
        self._dummy_password_hash = dummy_password_hash or generate_password_hash(
            secrets.token_urlsafe(32), method="scrypt"
        )
        if password_method == "scrypt":
            self._canonical_password_method = self._dummy_password_hash.partition("$")[
                0
            ]
        else:
            self._canonical_password_method = generate_password_hash(
                secrets.token_urlsafe(32), method=password_method
            ).partition("$")[0]
        self._needs_rehash = needs_rehash or (
            lambda encoded: _password_hash_needs_rehash(
                encoded, self._canonical_password_method
            )
        )

    def login(self, *, username: str, password: str, client_ip: str) -> IssuedSession:
        """Return opaque credentials or one generic authentication failure."""
        reservation = self._throttle.reserve(client_ip, username)
        completed = False
        try:
            try:
                secret = Password(password)
            except (TypeError, ValueError) as exc:
                self._throttle.record_failure(client_ip, username, reservation)
                completed = True
                raise AuthenticationError("invalid username or password") from exc

            with self._uow_factory() as uow:
                accounts = (
                    self._accounts_factory(uow)
                    if self._accounts_factory is not None
                    else PostgresAccountRepository(uow.connection)
                )
                account = accounts.get_by_normalized_username_for_update(username)
                verifier = self._verify_password
                if verifier is None:
                    from huginn.management.passwords import verify_password

                    verifier = verify_password
                encoded_hash = (
                    account.password_hash
                    if account is not None and account.status == "active"
                    else self._dummy_password_hash
                )
                verified = verifier(secret, encoded_hash)
                if account is None or account.status != "active" or not verified:
                    self._throttle.record_failure(client_ip, username, reservation)
                    completed = True
                    raise AuthenticationError("invalid username or password")

                sessions = (
                    self._sessions_factory(uow)
                    if self._sessions_factory is not None
                    else PostgresSessionRepository(uow.connection)
                )
                hasher = self._hash_password
                if hasher is None:
                    from huginn.management.passwords import hash_password

                    def hasher(value: Password) -> str:
                        return hash_password(value, method=self._password_method)

                if self._needs_rehash(account.password_hash):
                    updated = accounts.set_password_hash(account.id, hasher(secret))
                    if updated is None:
                        raise AuthenticationError("invalid username or password")
                issued = SessionService(
                    sessions,
                    clock=self._clock,
                    token_generator=self._token_generator,
                    ttl=self._config.session_ttl,
                ).create(account.id)
                uow.commit()
            self._throttle.record_success(client_ip, username, reservation)
            completed = True
            return issued
        finally:
            if not completed:
                self._throttle.release(reservation)


class PasswordChangeService:
    """Change an Account password and revoke all sessions atomically."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        *,
        accounts_factory: Callable[[Any], Any] | None = None,
        sessions_factory: Callable[[Any], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
        verify_password: Callable[[Password, str], bool] | None = None,
        hash_password: Callable[[Password], str] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._accounts_factory = accounts_factory
        self._sessions_factory = sessions_factory
        self._clock = clock
        self._verify_password = verify_password
        self._hash_password = hash_password

    def change_password(
        self, account_id: UUID, *, current_password: str, new_password: str
    ) -> None:
        try:
            current = Password(current_password)
            new = Password(new_password)
        except (TypeError, ValueError) as exc:
            raise ValidationDomainError("invalid password") from exc

        with self._uow_factory() as uow:
            accounts = (
                self._accounts_factory(uow)
                if self._accounts_factory is not None
                else PostgresAccountRepository(uow.connection)
            )
            account = accounts.get_by_id_for_update(account_id)
            verifier = self._verify_password
            if verifier is None:
                from huginn.management.passwords import verify_password

                verifier = verify_password
            if (
                account is None
                or account.status != "active"
                or not verifier(current, account.password_hash)
            ):
                raise AuthenticationError("current password is incorrect")

            hasher = self._hash_password
            if hasher is None:
                from huginn.management.passwords import hash_password

                hasher = hash_password
            updated = accounts.set_password_hash(account.id, hasher(new))
            if updated is None:
                raise AuthenticationError("current password is incorrect")
            sessions = (
                self._sessions_factory(uow)
                if self._sessions_factory is not None
                else PostgresSessionRepository(uow.connection)
            )
            SessionService(sessions, clock=self._clock).revoke_account(account.id)
            uow.commit()


@dataclass(frozen=True)
class ProvisionedIdentity:
    account_id: UUID
    user_id: UUID
    profile_id: UUID
    username: str
    status: str


class IdentityProvisioningService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        accounts: Any = None,
        users: Any = None,
        profiles: Any = None,
        hash_password: Callable[[Password], str] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._accounts, self._users, self._profiles = accounts, users, profiles
        self._hash_password = hash_password

    def provision(
        self,
        *,
        username: str,
        first_name: str,
        last_name: str,
        email: str,
        phone_number: str,
        country_of_residence: str,
        timezone: str | None,
        password: str,
    ) -> ProvisionedIdentity:
        try:
            identity = IdentityInput(
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone_number=phone_number,
                country_of_residence=country_of_residence,
                timezone=timezone,
            )
        except ValidationError as exc:
            allowed_fields = {
                "username",
                "first_name",
                "last_name",
                "email",
                "phone_number",
                "country_of_residence",
                "timezone",
            }
            fields = sorted(
                {
                    str(error["loc"][0])
                    for error in exc.errors()
                    if error.get("loc") and error["loc"][0] in allowed_fields
                }
            )
            detail = ", ".join(fields) if fields else "identity fields"
            raise ValidationDomainError(f"invalid identity fields: {detail}") from exc
        try:
            secret = Password(password)
        except (TypeError, ValueError) as exc:
            raise ValidationDomainError("invalid identity field: password") from exc

        with self._uow_factory() as uow:
            if self._accounts is None:
                accounts = PostgresAccountRepository(uow.connection)
                users = PostgresUserRepository(uow.connection)
                profiles = PostgresProfessionalProfileRepository(uow.connection)
            else:
                accounts, users, profiles = self._accounts, self._users, self._profiles
            if accounts.get_by_normalized_username(identity.username):
                raise ConflictError("username is already in use")
            hash_fn = self._hash_password
            if hash_fn is None:
                from huginn.management.passwords import hash_password

                hash_fn = hash_password
            account = accounts.create(NewAccount(identity.username, hash_fn(secret)))
            user = users.create(
                NewUser(
                    account.id,
                    identity.first_name,
                    identity.last_name,
                    identity.email,
                    identity.phone_number,
                    identity.country_of_residence,
                    identity.timezone,
                )
            )
            profile = profiles.create(NewProfessionalProfile(user.id))
            uow.commit()
            return ProvisionedIdentity(
                account.id, user.id, profile.id, account.username, account.status
            )


class AccountAdminService:
    def __init__(self, unit_of_work_factory: Callable[[], Any]) -> None:
        self._uow_factory = unit_of_work_factory

    def set_status(self, username: str, status: str) -> None:
        if status not in {"active", "disabled"}:
            raise ValidationDomainError("invalid account status")
        with self._uow_factory() as uow:
            accounts = PostgresAccountRepository(uow.connection)
            account = accounts.get_by_normalized_username(username)
            if account is None:
                raise NotFoundError("account not found")
            if accounts.set_status(account.id, status) is None:
                raise NotFoundError("account not found")
            if status == "disabled":
                with uow.connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE operational.sessions SET revoked_at = now() "
                        "WHERE account_id = %s AND revoked_at IS NULL",
                        (account.id,),
                    )
            uow.commit()

    def reset_password(self, username: str, password: str) -> None:
        try:
            secret = Password(password)
        except (TypeError, ValueError) as exc:
            raise ValidationDomainError("invalid identity field: password") from exc
        from huginn.management.passwords import hash_password

        with self._uow_factory() as uow:
            accounts = PostgresAccountRepository(uow.connection)
            account = accounts.get_by_normalized_username(username)
            if account is None:
                raise NotFoundError("account not found")
            if accounts.set_password_hash(account.id, hash_password(secret)) is None:
                raise NotFoundError("account not found")
            with uow.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE operational.sessions SET revoked_at = now() "
                    "WHERE account_id = %s AND revoked_at IS NULL",
                    (account.id,),
                )
            uow.commit()

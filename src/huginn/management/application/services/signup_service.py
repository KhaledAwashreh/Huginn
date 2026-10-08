"""Public signup and private lifecycle operations; lifecycle design sections 1–4."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from huginn.management.application.constants.lifecycle_policy import (
    COUNTRY_CALLING_CODES,
    MAIL_COOLDOWN_SECONDS,
)
from huginn.management.application.errors.errors import AuthorizationError
from huginn.management.application.errors.lifecycle import (
    LifecycleIntegrityError,
    LifecycleRateLimitError,
)
from huginn.management.application.protocols.lifecycle_mail_outbox import (
    LifecycleMailOutboxRepository,
)
from huginn.management.application.protocols.lifecycle_throttle import (
    LifecycleThrottleRepository,
)
from huginn.management.application.protocols.proof_cipher import ProofCipher
from huginn.management.application.read_models.lifecycle_mail_message import (
    LifecycleMailMessage,
)
from huginn.management.application.read_models.lifecycle_mail_outbox import (
    LifecycleMailOutboxRecord,
)
from huginn.management.application.requests.signup_request import SignupRequest
from huginn.management.application.responses.signup_response import SignupResponse
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.account import Account
from huginn.management.domain.entities.account_lifecycle_proof import (
    AccountLifecycleProof,
)
from huginn.management.domain.entities.account_recovery_identity import (
    AccountRecoveryIdentity,
)
from huginn.management.domain.entities.user import User
from huginn.management.domain.errors.errors import ConflictError, ValidationDomainError
from huginn.management.domain.errors.lifecycle import LifecycleProofError
from huginn.management.domain.services.identity_validation import (
    validated_identity_fields,
)
from huginn.management.domain.value_objects.account import NewAccount
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.professional_profile import (
    NewProfessionalProfile,
)
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose
from huginn.management.domain.value_objects.user import NewUser
from huginn.management.persistence.contracts.repositories.account import (
    AccountRepository,
)
from huginn.management.persistence.contracts.repositories.account_lifecycle_proof import (
    AccountLifecycleProofRepository,
)
from huginn.management.persistence.contracts.repositories.account_recovery_identity import (
    AccountRecoveryIdentityRepository,
)
from huginn.management.persistence.contracts.repositories.professional_profile import (
    ProfessionalProfileRepository,
)
from huginn.management.persistence.contracts.repositories.session import (
    SessionRepository,
)
from huginn.management.persistence.contracts.repositories.user import UserRepository
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol
from huginn.management.security.lifecycle_proofs import (
    digest_lifecycle_proof,
    generate_lifecycle_proof,
)
from huginn.management.security.passwords import (
    Password,
    hash_password,
    validate_new_password,
)


class _LifecycleOperations:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        config: ManagementConfig,
        *,
        cipher: ProofCipher | None,
        accounts_factory: Callable[[UnitOfWorkProtocol], AccountRepository],
        users_factory: Callable[[UnitOfWorkProtocol], UserRepository],
        profiles_factory: Callable[[UnitOfWorkProtocol], ProfessionalProfileRepository],
        recovery_identities_factory: Callable[
            [UnitOfWorkProtocol], AccountRecoveryIdentityRepository
        ],
        proofs_factory: Callable[[UnitOfWorkProtocol], AccountLifecycleProofRepository],
        outbox_factory: Callable[[UnitOfWorkProtocol], LifecycleMailOutboxRepository],
        throttle_factory: Callable[[UnitOfWorkProtocol], LifecycleThrottleRepository],
        sessions_factory: Callable[[UnitOfWorkProtocol], SessionRepository]
        | None = None,
        clock: Callable[[], datetime] | None = None,
        token_generator: Callable[[], str] | None = None,
        hash_password_fn: Callable[[Password], str] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._config = config
        self._cipher = cipher
        self._accounts_factory = accounts_factory
        self._users_factory = users_factory
        self._profiles_factory = profiles_factory
        self._recovery_factory = recovery_identities_factory
        self._proofs_factory = proofs_factory
        self._outbox_factory = outbox_factory
        self._throttle_factory = throttle_factory
        self._sessions_factory = sessions_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token_generator = token_generator or generate_lifecycle_proof
        self._hash_password = hash_password_fn or hash_password

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("lifecycle clock must be timezone-aware")
        return now.astimezone(UTC)

    def _admit(
        self, client_ip: str, username: str | None = None, email: str | None = None
    ) -> None:
        now = self._now()
        with self._uow_factory() as uow:
            repo = self._throttle_factory(uow)
            results = []
            if username is not None:
                results.append(
                    repo.reserve(
                        "receipt_username",
                        sha256(username.strip().lower().encode()).hexdigest(),
                        now,
                        limit=self._config.receipt_username_limit,
                        window=timedelta(hours=1),
                    )
                )
            if email is not None:
                results.append(
                    repo.reserve(
                        "receipt_email",
                        sha256(email.strip().lower().encode()).hexdigest(),
                        now,
                        limit=self._config.receipt_email_limit,
                        window=timedelta(hours=1),
                    )
                )
            receipt = username is not None or email is not None
            scope = "receipt_ip" if receipt else "proof_ip"
            results.append(
                repo.reserve(
                    scope,
                    sha256(client_ip.encode()).hexdigest(),
                    now,
                    limit=self._config.receipt_ip_limit
                    if receipt
                    else self._config.proof_ip_limit,
                    window=timedelta(hours=1) if receipt else timedelta(minutes=1),
                )
            )
            uow.commit()
        rejected = [r.retry_after_seconds for r in results if not r.allowed]
        if rejected:
            raise LifecycleRateLimitError(
                "Too many requests. Try again later", max(rejected)
            )

    def _identity(
        self, uow: UnitOfWorkProtocol, account_id: UUID
    ) -> AccountRecoveryIdentity:
        identity = self._recovery_factory(uow).get_by_account_id(account_id)
        if identity is None:
            raise LifecycleIntegrityError("Account security data is unavailable")
        return identity

    def _queue(
        self,
        uow: UnitOfWorkProtocol,
        account: Account,
        purpose: ProofPurpose,
        destination: str,
        *,
        cooldown: bool = True,
    ) -> bool:
        now = self._now()
        outbox = self._outbox_factory(uow)
        latest = outbox.last_enqueued_at(account.id, purpose)
        if (
            cooldown
            and latest is not None
            and now < latest + timedelta(seconds=MAIL_COOLDOWN_SECONDS)
        ):
            return False
        if self._cipher is None:
            raise LifecycleIntegrityError("Account mail delivery is unavailable")
        token = self._token_generator()
        ttl = (
            self._config.verification_ttl_seconds
            if purpose == ProofPurpose.VERIFY_EMAIL
            else self._config.reset_ttl_seconds
        )
        proof = AccountLifecycleProof(
            uuid4(),
            account.id,
            digest_lifecycle_proof(token),
            purpose,
            destination,
            now + timedelta(seconds=ttl),
            None,
            False,
            now,
        )
        self._proofs_factory(uow).replace(proof)
        outbox.enqueue(
            LifecycleMailOutboxRecord(
                uuid4(),
                account.id,
                proof.id,
                purpose.value,
                self._cipher.encrypt(
                    LifecycleMailMessage(destination, purpose.value, token)
                ),
                now,
            )
        )
        return True

    def _proof(
        self, uow: UnitOfWorkProtocol, token: str, purpose: ProofPurpose
    ) -> tuple[Account, AccountLifecycleProof]:
        try:
            digest = digest_lifecycle_proof(token)
        except ValueError as exc:
            raise LifecycleProofError("This link is invalid or expired") from exc
        repo = self._proofs_factory(uow)
        located = repo.get_by_digest(digest)
        if located is None:
            raise LifecycleProofError("This link is invalid or expired")
        account = self._accounts_factory(uow).get_by_id_for_update(located.account_id)
        if account is None:
            raise LifecycleProofError("This link is invalid or expired")
        identity = self._identity(uow, located.account_id)
        proof = repo.get_by_digest(digest)
        destination = (
            identity.pending_email
            if purpose == ProofPurpose.VERIFY_EMAIL
            else identity.verified_email
        )
        if (
            account is None
            or account.status != "active"
            or proof is None
            or proof.account_id != account.id
            or proof.purpose != purpose
            or proof.destination != destination
            or proof.consumed_at is not None
            or proof.superseded
            or proof.expires_at <= self._now()
        ):
            raise LifecycleProofError("This link is invalid or expired")
        return account, proof

    def _owner(
        self, uow: UnitOfWorkProtocol, principal: Principal
    ) -> tuple[Account, User]:
        account = self._accounts_factory(uow).get_by_id_for_update(principal.account_id)
        user = self._users_factory(uow).get_by_id(principal.user_id)
        if (
            account is None
            or account.status != "active"
            or user is None
            or user.account_id != principal.account_id
        ):
            raise AuthorizationError("Account access is unavailable")
        return account, user


class SignupService(_LifecycleOperations):
    def execute(self, request: SignupRequest) -> SignupResponse:
        fields = validated_identity_fields(
            username=request.username,
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            phone_number=request.phone_number,
            country_of_residence=request.country_of_residence,
            timezone=request.timezone,
        )
        prefix = COUNTRY_CALLING_CODES.get(fields[5])
        if (
            prefix is None
            or not fields[4].startswith(prefix)
            or len(fields[4]) - len(prefix) < 3
        ):
            raise ValidationDomainError("invalid identity field: country_of_residence")
        try:
            password = validate_new_password(request.password)
        except (TypeError, ValueError) as exc:
            raise ValidationDomainError("invalid identity field: password") from exc
        self._admit(request.client_ip, fields[0], fields[3])
        encoded = self._hash_password(password)
        try:
            with self._uow_factory() as uow:
                accounts = self._accounts_factory(uow)
                if (
                    accounts.get_by_normalized_username(fields[0]) is not None
                    or self._users_factory(uow).get_by_email(fields[3]) is not None
                    or self._recovery_factory(uow).get_by_email(fields[3]) is not None
                ):
                    return SignupResponse()
                account = accounts.create(NewAccount(fields[0], encoded))
                user = self._users_factory(uow).create(NewUser(account.id, *fields[1:]))
                self._profiles_factory(uow).create(NewProfessionalProfile(user.id))
                self._recovery_factory(uow).create(
                    account.id, verification_required=True, pending_email=fields[3]
                )
                self._queue(
                    uow, account, ProofPurpose.VERIFY_EMAIL, fields[3], cooldown=False
                )
                uow.commit()
        except ConflictError as exc:
            if getattr(exc.__cause__, "constraint_name", None) not in {
                "accounts_username_lower_key",
                "users_email_lower_key",
                "account_recovery_identity_email_lower_key",
            }:
                raise
        return SignupResponse()

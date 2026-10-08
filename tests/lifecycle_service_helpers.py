from dataclasses import replace
from uuid import uuid4

import psycopg
from cryptography.fernet import Fernet

from huginn.management.application.requests.signup_request import SignupRequest
from huginn.management.config import ManagementConfig
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.repositories.account import PostgresAccountRepository
from huginn.management.persistence.repositories.account_lifecycle_proof import (
    PostgresAccountLifecycleProofRepository,
)
from huginn.management.persistence.repositories.account_recovery_identity import (
    PostgresAccountRecoveryIdentityRepository,
)
from huginn.management.persistence.repositories.lifecycle_mail_outbox import (
    PostgresLifecycleMailOutboxRepository,
)
from huginn.management.persistence.repositories.lifecycle_throttle import (
    PostgresLifecycleThrottleRepository,
)
from huginn.management.persistence.repositories.professional_profile import (
    PostgresProfessionalProfileRepository,
)
from huginn.management.persistence.repositories.session import PostgresSessionRepository
from huginn.management.persistence.repositories.user import PostgresUserRepository
from huginn.management.security.encrypted_proof_cipher import EncryptedProofCipher


def signup_request(**changes):
    return replace(
        SignupRequest(
            str(uuid4()),
            "SignUp!12345",
            "Ada",
            "Lovelace",
            f"{uuid4()}@example.test",
            "+445555550123",
            "GB",
            str(uuid4()),
        ),
        **changes,
    )


def services(url, **overrides):
    config = ManagementConfig(
        database_url=url, lifecycle_proof_key=Fernet.generate_key().decode()
    )
    cipher = EncryptedProofCipher(config.lifecycle_proof_key)
    kwargs = {"cipher": cipher, "hash_password_fn": lambda p: "test-password-hash"}
    for name, repo in {
        "accounts": PostgresAccountRepository,
        "users": PostgresUserRepository,
        "profiles": PostgresProfessionalProfileRepository,
        "recovery_identities": PostgresAccountRecoveryIdentityRepository,
        "proofs": PostgresAccountLifecycleProofRepository,
        "outbox": PostgresLifecycleMailOutboxRepository,
        "throttle": PostgresLifecycleThrottleRepository,
        "sessions": PostgresSessionRepository,
    }.items():
        kwargs[name + "_factory"] = lambda uow, cls=repo: cls(uow.connection)
    kwargs.update(overrides)
    return lambda cls: cls(
        lambda: UnitOfWork(ManagementConnectionFactory(url)), config, **kwargs
    ), cipher


def account(url, username):
    with psycopg.connect(url) as conn:
        return conn.execute(
            "SELECT a.id,u.id FROM operational.accounts a JOIN operational.users u ON u.account_id=a.id WHERE username=%s",
            (username,),
        ).fetchone()


def queued(url, cipher, account_id, purpose):
    with psycopg.connect(url) as conn:
        payload = conn.execute(
            "SELECT encrypted_payload FROM operational.lifecycle_mail_outbox WHERE account_id=%s AND purpose=%s ORDER BY created_at DESC LIMIT 1",
            (account_id, purpose),
        ).fetchone()[0]
    return cipher.decrypt(bytes(payload))

from uuid import uuid4

import psycopg

from huginn.management.application.commands.provisioning import ProvisionIdentity
from huginn.management.application.services.provisioning import (
    IdentityProvisioningService,
)
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.unit_of_work import UnitOfWork
from huginn.management.persistence.repositories.account import PostgresAccountRepository
from huginn.management.persistence.repositories.account_recovery_identity import (
    PostgresAccountRecoveryIdentityRepository,
)
from huginn.management.persistence.repositories.professional_profile import (
    PostgresProfessionalProfileRepository,
)
from huginn.management.persistence.repositories.user import PostgresUserRepository


def test_owner_provisioning_creates_trusted_recovery_identity(
    management_database_url,
):
    username = f"Trusted-{uuid4()}"
    factory = ManagementConnectionFactory(management_database_url)
    service = IdentityProvisioningService(
        lambda: UnitOfWork(factory),
        accounts_factory=lambda uow: PostgresAccountRepository(uow.connection),
        users_factory=lambda uow: PostgresUserRepository(uow.connection),
        profiles_factory=lambda uow: PostgresProfessionalProfileRepository(
            uow.connection
        ),
        recovery_identities_factory=lambda uow: (
            PostgresAccountRecoveryIdentityRepository(uow.connection)
        ),
        hash_password_fn=lambda _: "trusted-test-hash",
    )

    identity = service.provision(
        ProvisionIdentity(
            username,
            "Ada",
            "Lovelace",
            f"{username.lower()}@example.test",
            "+12025550123",
            "US",
            "UTC",
            "a sufficiently long password",
        )
    )

    try:
        with psycopg.connect(management_database_url) as connection:
            contact_email = connection.execute(
                "SELECT email FROM operational.users WHERE account_id = %s",
                (identity.account_id,),
            ).fetchone()[0]
            recovery_identity = connection.execute(
                "SELECT verification_required, pending_email, verified_email, verified_at "
                "FROM operational.account_recovery_identity WHERE account_id = %s",
                (identity.account_id,),
            ).fetchone()

        assert contact_email == f"{username.lower()}@example.test"
        assert recovery_identity == (False, None, None, None)
    finally:
        with psycopg.connect(management_database_url) as connection:
            connection.execute(
                "DELETE FROM operational.account_recovery_identity WHERE account_id = %s",
                (identity.account_id,),
            )
            connection.execute(
                "DELETE FROM operational.professional_profiles WHERE user_id = %s",
                (identity.user_id,),
            )
            connection.execute(
                "DELETE FROM operational.users WHERE id = %s", (identity.user_id,)
            )
            connection.execute(
                "DELETE FROM operational.accounts WHERE id = %s",
                (identity.account_id,),
            )

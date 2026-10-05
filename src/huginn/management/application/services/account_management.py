"""Application services supplied to the owner administration CLI."""

from dataclasses import dataclass

from huginn.management.application.services.account_admin import AccountAdminService
from huginn.management.application.services.provisioning import (
    IdentityProvisioningService,
)


@dataclass(frozen=True)
class AccountAdministrationServices:
    provisioning: IdentityProvisioningService
    lifecycle: AccountAdminService

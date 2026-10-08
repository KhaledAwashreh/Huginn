"""Lifecycle application response."""

from dataclasses import dataclass

from huginn.management.application.read_models.account_security import AccountSecurity


@dataclass(frozen=True, slots=True)
class GetAccountSecurityResponse:
    security: AccountSecurity

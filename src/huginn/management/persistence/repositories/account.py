"""PostgreSQL account repository."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.account import Account
from huginn.management.domain.value_objects.account import NewAccount
from huginn.management.persistence.contracts.repositories.account import (
    AccountRepository,
)
from huginn.management.persistence.errors.database import IntegrityError
from huginn.management.persistence.repositories.common import PostgresIdentityRepository


class PostgresAccountRepository(PostgresIdentityRepository, AccountRepository):
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
                "INSERT INTO operational.accounts (username, password_hash, status) "
                f"VALUES (%s, %s, %s) RETURNING {self._columns}",
                (account.username.strip(), account.password_hash, account.status),
            )
            return self._map(row)
        except IntegrityError as exc:
            raise self._translate(exc) from exc

    def set_status(self, account_id: UUID, status: str) -> Account | None:
        row = self._one(
            "UPDATE operational.accounts SET status = %s, updated_at = clock_timestamp() "
            f"WHERE id = %s RETURNING {self._columns}",
            (status, account_id),
        )
        return self._map(row) if row else None

    def set_password_hash(self, account_id: UUID, password_hash: str) -> Account | None:
        row = self._one(
            "UPDATE operational.accounts SET password_hash = %s, "
            f"updated_at = clock_timestamp() WHERE id = %s RETURNING {self._columns}",
            (password_hash, account_id),
        )
        return self._map(row) if row else None

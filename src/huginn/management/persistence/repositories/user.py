"""PostgreSQL user repository."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.user import User
from huginn.management.domain.value_objects.user import NewUser, UserChanges
from huginn.management.persistence.contracts.repositories.user import UserRepository
from huginn.management.persistence.errors.database import IntegrityError
from huginn.management.persistence.repositories.common import PostgresIdentityRepository


class PostgresUserRepository(PostgresIdentityRepository, UserRepository):
    _columns = (
        "id, account_id, first_name, last_name, email, phone_number, "
        "country_of_residence, timezone, created_at, updated_at"
    )

    @staticmethod
    def _map(row: tuple[Any, ...]) -> User:
        return User(*row)

    def get_by_id(self, user_id: UUID) -> User | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.users WHERE id = %s", (user_id,)
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
                "INSERT INTO operational.users (account_id, first_name, last_name, email, "
                "phone_number, country_of_residence, timezone) "
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
        except IntegrityError as exc:
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
        except IntegrityError as exc:
            raise self._translate(exc) from exc
        return self._map(row) if row else None

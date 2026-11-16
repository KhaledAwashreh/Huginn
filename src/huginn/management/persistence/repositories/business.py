"""PostgreSQL persistence for Business ownership and profile fields."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.business import Business
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.business_changes import BusinessChanges
from huginn.management.domain.value_objects.new_business import NewBusiness
from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)
from huginn.management.persistence.contracts.repositories.business import (
    BusinessRepository,
)
from huginn.management.persistence.errors.database import IntegrityError
from huginn.management.persistence.repositories.common import PostgresIdentityRepository


class PostgresBusinessRepository(PostgresIdentityRepository, BusinessRepository):
    _columns = (
        "id, owner_user_id, name, tagline, website, location, description, "
        "capabilities, created_at, updated_at"
    )
    _update_columns = {
        "name": "name",
        "tagline": "tagline",
        "website": "website",
        "location": "location",
        "description": "description",
        "capabilities": "capabilities",
    }

    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    @staticmethod
    def _map(row: tuple[Any, ...]) -> Business:
        capabilities = (
            tuple(dict(item) for item in row[7]) if row[7] is not None else None
        )
        return Business(*row[:7], capabilities, *row[8:])

    def get_by_id(self, business_id: UUID) -> Business | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.businesses WHERE id=%s",
            (business_id,),
        )
        return self._map(row) if row else None

    def get_by_owner_user_id(self, owner_user_id: UUID) -> Business | None:
        row = self._one(
            f"SELECT {self._columns} FROM operational.businesses "
            "WHERE owner_user_id=%s",
            (owner_user_id,),
        )
        return self._map(row) if row else None

    def create(self, business: NewBusiness) -> Business:
        try:
            row = self._write(
                "WITH created_business AS ("
                "INSERT INTO operational.businesses(owner_user_id) VALUES (%s) "
                f"RETURNING {self._columns}), created_preferences AS ("
                "INSERT INTO operational.business_recommendation_preferences(business_id) "
                "SELECT id FROM created_business RETURNING business_id) "
                f"SELECT {self._columns} FROM created_business",
                (business.owner_user_id,),
            )
        except IntegrityError as exc:
            if exc.constraint_name == "businesses_owner_user_id_key":
                raise ConflictError("User already owns a Business") from exc
            raise self._translate(exc) from exc
        return self._map(row)

    def update(self, business_id: UUID, changes: BusinessChanges) -> Business | None:
        supplied = changes.supplied_fields
        if not supplied:
            return self.get_by_id(business_id)
        if supplied - self._update_columns.keys():
            raise ValueError("unsupported Business update field")
        fields = sorted(supplied)
        assignments = ", ".join(f"{self._update_columns[field]}=%s" for field in fields)
        params = tuple(
            JsonParameter([dict(item) for item in changes.values[field]])
            if field == "capabilities" and changes.values[field] is not None
            else changes.values[field]
            for field in fields
        )
        try:
            row = self._one(
                f"UPDATE operational.businesses SET {assignments}, "
                "updated_at=clock_timestamp() WHERE id=%s "
                f"RETURNING {self._columns}",
                (*params, business_id),
            )
        except IntegrityError as exc:
            raise self._translate(exc) from exc
        return self._map(row) if row else None

"""PostgreSQL professional profile repository."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.professional_profile import ProfessionalProfile
from huginn.management.domain.value_objects.professional_profile import (
    NewProfessionalProfile,
    ProfessionalProfileChanges,
)
from huginn.management.persistence.contracts.database import JsonParameter
from huginn.management.persistence.contracts.repositories.professional_profile import (
    ProfessionalProfileRepository,
)
from huginn.management.persistence.errors.database import IntegrityError
from huginn.management.persistence.repositories.common import PostgresIdentityRepository
from huginn.management.persistence.row_models.resources import (
    ProfessionalCollectionsRow,
)


class PostgresProfessionalProfileRepository(
    PostgresIdentityRepository, ProfessionalProfileRepository
):
    _columns = (
        "id, user_id, headline, professional_summary, skills, experience, "
        "previous_projects, created_at, updated_at"
    )

    @staticmethod
    def _map(row: tuple[Any, ...]) -> ProfessionalProfile:
        collections = ProfessionalCollectionsRow.model_validate(
            {
                "skills": list(row[4]),
                "experience": list(row[5]),
                "previous_projects": list(row[6]),
            }
        ).model_dump(mode="json")
        return ProfessionalProfile(
            row[0],
            row[1],
            row[2],
            row[3],
            tuple(collections["skills"]),
            tuple(collections["experience"]),
            tuple(collections["previous_projects"]),
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
                "INSERT INTO operational.professional_profiles (user_id) VALUES (%s) "
                f"RETURNING {self._columns}",
                (profile.user_id,),
            )
            return self._map(row)
        except IntegrityError as exc:
            raise self._translate(exc) from exc

    def update(
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
            JsonParameter([dict(item) for item in changes.values[name]])
            if name in {"skills", "experience", "previous_projects"}
            else changes.values[name]
            for name in fields
        )
        try:
            row = self._one(
                f"UPDATE operational.professional_profiles SET {assignments}, "
                "updated_at = clock_timestamp() WHERE user_id = %s "
                f"RETURNING {self._columns}",
                (*parameters, user_id),
            )
        except IntegrityError as exc:
            raise self._translate(exc) from exc
        return self._map(row) if row else None

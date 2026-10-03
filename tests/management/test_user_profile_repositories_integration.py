from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError

from huginn.management.domain.account import NewAccount
from huginn.management.domain.professional_profile import (
    NewProfessionalProfile,
    ProfessionalProfileChanges,
)
from huginn.management.domain.user import (
    NewUser,
    UserChanges,
)
from huginn.management.repositories.postgres.account import PostgresAccountRepository
from huginn.management.repositories.postgres.professional_profile import (
    PostgresProfessionalProfileRepository,
)
from huginn.management.repositories.postgres.user import PostgresUserRepository


def test_profile_repositories_validate_jsonb_map_partial_updates_and_leave_rollback(
    management_database_url,
):
    username = f"Profile-{uuid4()}"
    with psycopg.connect(management_database_url) as connection:
        connection.execute("SAVEPOINT user_profile_repositories")
        accounts = PostgresAccountRepository(connection)
        users = PostgresUserRepository(connection)
        profiles = PostgresProfessionalProfileRepository(connection)
        account = accounts.create(NewAccount(username, "scrypt$placeholder"))
        user = users.create(
            NewUser(
                account.id,
                "Ada",
                "Lovelace",
                f"{username}@example.test",
                "+12025550123",
                "US",
                "UTC",
            )
        )
        profile = profiles.create(NewProfessionalProfile(user.id))

        connection.execute(
            "UPDATE operational.users SET updated_at = now() - interval '1 day' "
            "WHERE id = %s",
            (user.id,),
        )
        connection.execute(
            "UPDATE operational.professional_profiles "
            "SET updated_at = now() - interval '1 day' WHERE id = %s",
            (profile.id,),
        )
        user = users.get_by_id(user.id)
        profile = profiles.get_owned(user.id)

        updated_user = users.update(
            user.id,
            UserChanges(
                {"first_name": "Grace", "timezone": None},
                frozenset({"first_name", "timezone"}),
            ),
        )
        assert updated_user.first_name == "Grace"
        assert updated_user.timezone is None
        assert updated_user.updated_at > user.updated_at

        updated_profile = profiles.update(
            user.id,
            ProfessionalProfileChanges(
                {
                    "headline": None,
                    "professional_summary": "A summary",
                    "skills": ({"name": "Python"}, {"name": "Python"}),
                    "experience": (
                        {
                            "organization": "Acme",
                            "role": "Engineer",
                            "start_month": "2024-01",
                            "is_current": True,
                        },
                    ),
                    "previous_projects": ({"name": "API", "description": "Built it"},),
                },
                frozenset(
                    {
                        "headline",
                        "professional_summary",
                        "skills",
                        "experience",
                        "previous_projects",
                    }
                ),
            ),
        )
        assert updated_profile.headline is None
        assert updated_profile.skills == ({"name": "Python"}, {"name": "Python"})
        assert updated_profile.experience[0]["organization"] == "Acme"
        assert updated_profile.previous_projects[0]["name"] == "API"
        assert updated_profile.updated_at > profile.updated_at
        assert (
            users.update(
                uuid4(), UserChanges({"first_name": "Other"}, frozenset({"first_name"}))
            )
            is None
        )
        assert (
            profiles.update(uuid4(), ProfessionalProfileChanges({}, frozenset()))
            is None
        )

        connection.execute(
            "UPDATE operational.professional_profiles "
            'SET experience = \'[{"organization": "Acme"}]\'::jsonb '
            "WHERE user_id = %s",
            (user.id,),
        )
        with pytest.raises(ValidationError):
            profiles.get_owned(user.id)

        connection.execute("ROLLBACK TO SAVEPOINT user_profile_repositories")
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.accounts WHERE username = %s",
                (username,),
            ).fetchone()[0]
            == 0
        )
        connection.execute("RELEASE SAVEPOINT user_profile_repositories")

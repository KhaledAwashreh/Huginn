from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.account import NewAccount
from huginn.management.domain.value_objects.business_changes import BusinessChanges
from huginn.management.domain.value_objects.business_recommendation_preferences import (
    BusinessRecommendationPreferencesChanges,
)
from huginn.management.domain.value_objects.new_business import NewBusiness
from huginn.management.domain.value_objects.user import NewUser
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.account import PostgresAccountRepository
from huginn.management.persistence.repositories.business import (
    PostgresBusinessRepository,
)
from huginn.management.persistence.repositories.business_recommendation_preferences import (
    PostgresBusinessRecommendationPreferencesRepository,
)
from huginn.management.persistence.repositories.user import PostgresUserRepository


def test_business_repository_preserves_unset_fields_and_rejects_second_owner(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        connection.execute("SAVEPOINT business_repository")
        before_businesses = connection.execute(
            "SELECT count(*) FROM operational.businesses"
        ).fetchone()[0]
        session = PsycopgDatabaseSession(connection)
        account = PostgresAccountRepository(session).create(
            NewAccount(f"business-{uuid4()}", "test-hash")
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.businesses"
            ).fetchone()[0]
            == before_businesses
        )
        user = PostgresUserRepository(session).create(
            NewUser(
                account.id,
                "Ada",
                "Lovelace",
                f"{uuid4()}@example.test",
                "+12025550123",
                "US",
            )
        )
        businesses = PostgresBusinessRepository(session)
        persisted = businesses.get_by_owner_user_id(user.id)
        assert persisted is not None
        assert (
            persisted.name,
            persisted.tagline,
            persisted.website,
            persisted.location,
            persisted.description,
            persisted.capabilities,
        ) == (None, None, None, None, None, None)
        preferences = PostgresBusinessRecommendationPreferencesRepository(session)
        cadence = preferences.get(persisted.id)
        assert cadence.repeat_interval_days == 30
        assert connection.execute(
            "INSERT INTO operational.professional_profiles (user_id, headline, skills) "
            "VALUES (%s,'Independent consultant','[{\"name\":\"Forecasting\"}]') "
            "RETURNING headline,skills",
            (user.id,),
        ).fetchone() == ("Independent consultant", [{"name": "Forecasting"}])
        updated = businesses.update(
            persisted.id,
            BusinessChanges(
                {
                    "name": "Lovelace Studio",
                    "website": "https://example.test",
                    "capabilities": ({"name": "Analytics"},),
                },
                frozenset({"name", "website", "capabilities"}),
            ),
        )
        assert businesses.get_by_id(persisted.id) == updated
        assert (updated.name, updated.website, updated.capabilities) == (
            "Lovelace Studio",
            "https://example.test",
            ({"name": "Analytics"},),
        )
        assert connection.execute(
            "SELECT headline,skills FROM operational.professional_profiles WHERE user_id=%s",
            (user.id,),
        ).fetchone() == ("Independent consultant", [{"name": "Forecasting"}])
        cadence_repository = PostgresBusinessRecommendationPreferencesRepository(
            session
        )
        assert cadence_repository.get(persisted.id).repeat_interval_days == 30
        updated_cadence = cadence_repository.update(
            persisted.id, BusinessRecommendationPreferencesChanges(45)
        )
        assert updated_cadence.repeat_interval_days == 45
        assert cadence_repository.get(persisted.id) == updated_cadence
        with pytest.raises(ConflictError):
            businesses.create(NewBusiness(user.id))
        connection.execute("ROLLBACK TO SAVEPOINT business_repository")
        connection.execute("RELEASE SAVEPOINT business_repository")


def test_user_delete_removes_only_blank_business_and_preferences(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        session = PsycopgDatabaseSession(connection)
        users = PostgresUserRepository(session)
        accounts = PostgresAccountRepository(session)
        business_repository = PostgresBusinessRepository(session)
        preferences = PostgresBusinessRecommendationPreferencesRepository(session)

        blank_account = accounts.create(NewAccount(f"blank-{uuid4()}", "test-hash"))
        blank_user = users.create(
            NewUser(
                blank_account.id,
                "Ada",
                "Lovelace",
                f"{uuid4()}@example.test",
                "+12025550123",
                "US",
            )
        )
        blank_business = business_repository.get_by_owner_user_id(blank_user.id)
        assert blank_business is not None
        assert preferences.get(blank_business.id) is not None
        connection.execute(
            "DELETE FROM operational.users WHERE id=%s", (blank_user.id,)
        )
        assert business_repository.get_by_id(blank_business.id) is None
        assert preferences.get(blank_business.id) is None

        populated_account = accounts.create(
            NewAccount(f"populated-{uuid4()}", "test-hash")
        )
        populated_user = users.create(
            NewUser(
                populated_account.id,
                "Ada",
                "Lovelace",
                f"{uuid4()}@example.test",
                "+12025550123",
                "US",
            )
        )
        populated_business = business_repository.get_by_owner_user_id(populated_user.id)
        assert populated_business is not None
        connection.execute(
            "INSERT INTO operational.service_offerings(business_id,name,description) "
            "VALUES (%s,'Consulting','Review')",
            (populated_business.id,),
        )
        with pytest.raises(psycopg.IntegrityError), connection.transaction():
            connection.execute(
                "DELETE FROM operational.users WHERE id=%s", (populated_user.id,)
            )
        assert users.get_by_id(populated_user.id) is not None
        assert business_repository.get_by_id(populated_business.id) is not None
        assert preferences.get(populated_business.id) is not None

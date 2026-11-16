from uuid import uuid4

import pytest

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from huginn.management.persistence.errors.database import DatabaseError


@pytest.mark.parametrize("release", ["commit", "rollback", "error"])
def test_shared_pair_lock_serializes_same_pair_and_releases_on_every_exit(
    management_database_url, release
):
    factory = ManagementConnectionFactory(
        management_database_url, statement_timeout_ms=200
    )
    business_id, company_id = uuid4(), uuid4()

    class ExpectedExit(Exception):
        pass

    try:
        with PostgresProspectingUnitOfWork(factory) as first:
            first.lock_business_company(business_id, company_id)
            with (
                pytest.raises(DatabaseError) as blocked,
                PostgresProspectingUnitOfWork(factory) as same_pair,
            ):
                same_pair.lock_business_company(business_id, company_id)
            assert blocked.value.sqlstate == "57014"
            with PostgresProspectingUnitOfWork(factory) as other_pair:
                other_pair.lock_business_company(business_id, uuid4())
                other_pair.rollback()
            if release == "error":
                raise ExpectedExit
            getattr(first, release)()
    except ExpectedExit:
        assert release == "error"
    with PostgresProspectingUnitOfWork(factory) as after_release:
        after_release.lock_business_company(business_id, company_id)
        after_release.rollback()


def test_read_snapshot_stays_coherent_across_a_concurrent_committed_save(
    management_database_url,
):
    import psycopg

    from huginn.management.application.requests.save_recommendation_request import (
        SaveRecommendationRequest,
    )
    from huginn.management.application.services.save_recommendation_service import (
        SaveRecommendationService,
    )
    from huginn.management.domain.value_objects.common import Principal
    from tests.management.persistence.prospecting_fixtures import (
        seed_owned_recommendation_revision,
    )

    with psycopg.connect(management_database_url) as connection:
        identity, recommendation, revision = seed_owned_recommendation_revision(
            connection
        )
    factory = ManagementConnectionFactory(
        management_database_url, statement_timeout_ms=1000
    )
    with PostgresProspectingUnitOfWork(factory, read_only=True) as reader:
        assert (
            reader.recommendations.get_owned(identity.business_id, recommendation.id)
            == recommendation
        )
        assert (
            reader.prospects.get_by_business_company(
                identity.business_id, identity.company_id
            )
            is None
        )
        saved = SaveRecommendationService(
            lambda: PostgresProspectingUnitOfWork(factory)
        ).execute(
            Principal(identity.account_id, identity.owner_user_id),
            SaveRecommendationRequest(recommendation.id, revision.id, "snapshot-save"),
        )
        assert (
            reader.recommendations.get_owned(identity.business_id, recommendation.id)
            == recommendation
        )
        assert (
            reader.prospects.get_by_business_company(
                identity.business_id, identity.company_id
            )
            is None
        )
        assert reader.origins.list_owned(identity.business_id, saved.prospect_id) == ()
    with PostgresProspectingUnitOfWork(factory, read_only=True) as reader:
        assert (
            reader.recommendations.get_owned(
                identity.business_id, recommendation.id
            ).status.value
            == "converted"
        )
        assert (
            reader.prospects.get_owned(
                identity.business_id, saved.prospect_id
            ).stage.value
            == "saved"
        )
        assert (
            reader.origins.list_owned(identity.business_id, saved.prospect_id)[
                0
            ].assessment_revision_id
            == revision.id
        )


def test_read_only_work_rejects_accidental_database_writes(management_database_url):
    import psycopg

    from huginn.management.domain.value_objects.business_recommendation_preferences import (
        BusinessRecommendationPreferencesChanges,
    )
    from tests.management.persistence.prospecting_fixtures import (
        seed_prospecting_owner_company,
    )

    with psycopg.connect(management_database_url) as connection:
        identity = seed_prospecting_owner_company(connection)
    factory = ManagementConnectionFactory(management_database_url)
    with (
        pytest.raises(DatabaseError) as rejected,
        PostgresProspectingUnitOfWork(factory, read_only=True) as reader,
    ):
        reader.business_recommendation_preferences.update(
            identity.business_id, BusinessRecommendationPreferencesChanges(45)
        )
    assert rejected.value.sqlstate == "25006"
    with PostgresProspectingUnitOfWork(factory, read_only=True) as reader:
        assert (
            reader.business_recommendation_preferences.get(
                identity.business_id
            ).repeat_interval_days
            == 30
        )

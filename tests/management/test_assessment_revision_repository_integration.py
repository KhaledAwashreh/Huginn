from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.errors.errors import ConflictError
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.assessment_revision import (
    PostgresAssessmentRevisionRepository,
)
from tests.management.persistence.prospecting_fixtures import (
    seed_owned_recommendation_revision,
)


def test_revision_roundtrips_detached_multi_strategy_snapshots_and_is_immutable(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        identity, selected, revision = seed_owned_recommendation_revision(connection)
        revisions = PostgresAssessmentRevisionRepository(
            PsycopgDatabaseSession(connection)
        )
        persisted = revisions.get_owned(identity.business_id, selected.id, revision.id)
        assert persisted == revision
        assert len(persisted.strategy_assessments) == 2
        assert [
            item.assessment_snapshot.value["score"]
            for item in persisted.strategy_assessments
        ] == [71, 70]
        assert persisted.professional_profile_snapshot.to_json_object() == {
            "headline": "Independent consultant",
            "skills": [{"name": "research"}],
        }
        assert [
            item.to_json_object()["source"] for item in persisted.evidence_snapshots
        ] == ["yc", "hn"]
        assert persisted.evidence_observation_ids == revision.evidence_observation_ids
        assert selected.current_revision_id == revision.id
        assert revisions.list_history(identity.business_id, selected.id) == (revision,)
        with pytest.raises(ConflictError):
            revisions.append(revision)
        assert revisions.get_owned(uuid4(), selected.id, revision.id) is None

"""Weekly email selects shared recommendation revisions without legacy batches."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from huginn.management.application.requests.mark_recommendation_not_relevant_request import (
    MarkRecommendationNotRelevantRequest,
)
from huginn.management.application.services.recommendation_decision_service import (
    RecommendationDecisionService,
)
from huginn.management.application.services.recommendation_generation import (
    RecommendationGenerationService,
)
from huginn.management.application.services.weekly_digest import WeeklyDigestService
from huginn.management.delivery.templates.weekly_digest import (
    PlainTextWeeklyDigestRenderer,
)
from huginn.management.domain.value_objects.common import Principal
from huginn.management.persistence.database.client import (
    ManagementConnectionFactory,
)
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from huginn.management.persistence.repositories.digest_subscription_access import (
    PostgresDigestSubscriptionAccess,
)
from huginn.management.persistence.repositories.recommendation_generation import (
    PostgresRecommendationGenerationSource,
)
from huginn.management.persistence.repositories.weekly_digest_content import (
    PostgresWeeklyDigestContentRepository,
)
from huginn.management.persistence.repositories.weekly_digest_delivery import (
    PostgresWeeklyDigestDeliveryRepository,
)
from tests.management.persistence.digest_subscription_fixtures import (
    seed_digest_subscriber,
)
from tests.matchmaking.evidence_fixtures import (
    reconcile as _reconcile,
)
from tests.matchmaking.evidence_fixtures import (
    seed_company as _seed_company,
)
from tests.postgres_harness import provisioned_postgres


@pytest.fixture
def weekly_matching_database_url():
    with provisioned_postgres("weekly_matching_integration") as url:
        with psycopg.connect(url, autocommit=True) as connection:
            for filename in (
                "operational-recommendations.sql",
                "operational-weekly-digest.sql",
                "operational-weekly-digest-content.sql",
            ):
                connection.execute(
                    (Path("db/schema") / filename).read_text(encoding="utf-8")
                )
        yield url


def _weekly_service(factory, generation, sender, clock):
    return WeeklyDigestService(
        lambda: PostgresProspectingUnitOfWork(factory),
        subscription_access_factory=lambda work: PostgresDigestSubscriptionAccess(
            work.connection
        ),
        delivery_repository_factory=lambda work: PostgresWeeklyDigestDeliveryRepository(
            work.connection
        ),
        content_repository_factory=lambda work: PostgresWeeklyDigestContentRepository(
            work.connection
        ),
        source_factory=PostgresRecommendationGenerationSource,
        generation=generation,
        renderer=PlainTextWeeklyDigestRenderer(
            "https://huginn.example", "integration-signing-key", "huginn.example"
        ),
        sender=sender,
        sender_address="weekly@huginn.example",
        clock=clock,
    )


def test_weekly_email_uses_shared_multi_strategy_revisions_and_distinct_companies(
    weekly_matching_database_url,
):
    url = weekly_matching_database_url
    now = datetime.now(UTC) + timedelta(seconds=1)
    with psycopg.connect(url) as connection:
        user, _, first_strategy = seed_digest_subscriber(
            connection, "weekly-integration"
        )
        business_id = connection.execute(
            "SELECT id FROM operational.businesses WHERE owner_user_id=%s", (user,)
        ).fetchone()[0]
        connection.execute(
            "UPDATE operational.service_offerings SET name='Directory research',"
            "description='Understand directory records' WHERE business_id=%s",
            (business_id,),
        )
        connection.execute(
            'UPDATE operational.ideal_client_profiles SET industries=\'[{"name":"SaaS"}]\','
            'company_sizes=\'[{"band":"0-10"}]\','
            'geographies=\'[{"kind":"country","value":"Germany"}]\' '
            "WHERE business_id=%s",
            (business_id,),
        )
        second_offering = connection.execute(
            "INSERT INTO operational.service_offerings(business_id,name,description) "
            "VALUES (%s,'Record research','Review directory records') RETURNING id",
            (business_id,),
        ).fetchone()[0]
        second_icp = connection.execute(
            "INSERT INTO operational.ideal_client_profiles"
            "(business_id,name,industries,company_sizes,geographies) "
            "VALUES (%s,'UK targets','[{\"name\":\"SaaS\"}]',"
            '\'[{"band":"0-10"}]\',\'[{"kind":"country","value":"UK"}]\') RETURNING id',
            (business_id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO operational.client_discovery_strategies"
            "(business_id,name,service_offering_id,ideal_client_profile_id,is_active) "
            "VALUES (%s,'UK strategy',%s,%s,true)",
            (business_id, second_offering, second_icp),
        )
        companies = []
        for country in ("DE", "DE", "DE", "UK", "UK", "UK", None, "US"):
            company, _ = _seed_company(connection, event_at=now - timedelta(days=1))
            connection.execute(
                "UPDATE gold.company SET country=%s WHERE id=%s", (country, company)
            )
            companies.append(company)
        connection.commit()
    _reconcile(url)

    factory = ManagementConnectionFactory(url)
    generation = RecommendationGenerationService(
        lambda: PostgresProspectingUnitOfWork(factory),
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: now,
    )
    with PostgresProspectingUnitOfWork(factory) as work:
        PostgresDigestSubscriptionAccess(work.connection).subscribe(
            user, business_id, now
        )
        work.commit()
    messages = []
    service_time = [now]

    class Sender:
        def send(self, message):
            messages.append(message)
            return service_time[0]

    class CaptureWeeklyGeneration:
        company_order = ()

        def execute_weekly(self, business_id):
            response = generation.execute_weekly(business_id)
            with psycopg.connect(url) as connection:
                self.company_order = tuple(
                    connection.execute(
                        "SELECT company_id FROM operational.assessment_revisions "
                        "WHERE id=%s",
                        (reference.revision_id,),
                    ).fetchone()[0]
                    for reference in response.references
                )
            return response

    weekly_generation = CaptureWeeklyGeneration()
    base_renderer = PlainTextWeeklyDigestRenderer(
        "https://huginn.example", "integration-signing-key", "huginn.example"
    )

    service = WeeklyDigestService(
        lambda: PostgresProspectingUnitOfWork(factory),
        subscription_access_factory=lambda work: PostgresDigestSubscriptionAccess(
            work.connection
        ),
        delivery_repository_factory=lambda work: PostgresWeeklyDigestDeliveryRepository(
            work.connection
        ),
        content_repository_factory=lambda work: PostgresWeeklyDigestContentRepository(
            work.connection
        ),
        source_factory=PostgresRecommendationGenerationSource,
        generation=weekly_generation,
        renderer=base_renderer,
        sender=Sender(),
        sender_address="weekly@huginn.example",
        clock=lambda: service_time[0],
    )
    original_authorize = service._authorize
    rejected_company_ids = []

    def authorize_after_owner_rejection(subscription, delivery, week_start, references):
        reference = references[0]
        with PostgresProspectingUnitOfWork(factory) as work:
            recommendation = work.recommendations.get_owned(
                business_id, reference.recommendation_id
            )
        assert recommendation is not None
        rejected_company_ids.append(recommendation.company_id)
        decided_at = now + timedelta(seconds=1)
        with psycopg.connect(url) as connection:
            account_id = connection.execute(
                "SELECT account_id FROM operational.users WHERE id=%s", (user,)
            ).fetchone()[0]
        RecommendationDecisionService(
            lambda: PostgresProspectingUnitOfWork(factory), clock=lambda: decided_at
        ).mark_not_relevant(
            Principal(account_id, user),
            MarkRecommendationNotRelevantRequest(
                reference.recommendation_id,
                reference.revision_id,
                recommendation.version,
                "reject-before-atomic-weekly-publication",
                "Intervening decision before email authorization",
            ),
        )
        service_time[0] = now + timedelta(seconds=2)
        return original_authorize(subscription, delivery, week_start, references)

    service._authorize = authorize_after_owner_rejection
    with PostgresProspectingUnitOfWork(factory) as work:
        subscription = PostgresDigestSubscriptionAccess(work.connection).list_eligible(
            1
        )[0]
    week_start = now.date() - timedelta(days=now.weekday())
    assert service._deliver(subscription, week_start, 100) == "sent"
    assert len(messages) == 1
    assert "/recommendations?recommendation_id=" in messages[0].body
    assert "batch=" not in messages[0].body

    with psycopg.connect(url) as connection:
        delivery, content_id = connection.execute(
            "SELECT id,current_content_id FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s",
            (business_id,),
        ).fetchone()
        members = connection.execute(
            "SELECT company_id,recommendation_id,assessment_revision_id,offer_cycle_id "
            "FROM operational.weekly_digest_members WHERE content_id=%s ORDER BY position",
            (content_id,),
        ).fetchall()
        assert len(members) == 6
        assert len({member[0] for member in members}) == 6
        assert {member[0] for member in members} == set(companies[:7]) - {
            rejected_company_ids[0]
        }
        assert tuple(member[0] for member in members) == tuple(
            company_id
            for company_id in weekly_generation.company_order
            if company_id != rejected_company_ids[0]
        )
        content_versions = connection.execute(
            "SELECT c.version,c.id,count(m.position) FROM operational.weekly_digest_contents c "
            "LEFT JOIN operational.weekly_digest_members m ON m.content_id=c.id "
            "WHERE c.delivery_id=%s GROUP BY c.version,c.id ORDER BY c.version",
            (delivery,),
        ).fetchall()
        assert [(version, count) for version, _, count in content_versions] == [
            (1, 6),
        ]
        assert content_id == content_versions[-1][1]
        assert connection.execute(
            "SELECT status,first_presented_at FROM operational.recommendations "
            "WHERE business_id=%s AND company_id=%s",
            (business_id, rejected_company_ids[0]),
        ).fetchone() == ("rejected", None)
        assert connection.execute(
            "SELECT count(*) FROM operational.offer_cycles "
            "WHERE business_id=%s AND company_id=%s",
            (business_id, rejected_company_ids[0]),
        ).fetchone() == (0,)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.recommendation_batches WHERE user_id=%s",
                (user,),
            ).fetchone()[0]
            == 0
        )
        for _, recommendation_id, revision_id, cycle_id in members:
            assert (
                connection.execute(
                    "SELECT current_revision_id FROM operational.recommendations WHERE id=%s",
                    (recommendation_id,),
                ).fetchone()[0]
                == revision_id
            )
            associations = connection.execute(
                "SELECT item->>'strategy_id',item->'assessment_snapshot'->>'score' "
                "FROM operational.assessment_revisions revision, "
                "jsonb_array_elements(revision.strategy_assessments) item "
                "WHERE revision.recommendation_id=%s AND revision.id=%s",
                (recommendation_id, revision_id),
            ).fetchall()
            assert 1 <= len(associations) <= 2
            scores = {int(score) for _, score in associations}
            assert all(0 <= score <= 100 for score in scores)
            assert all(
                f"Strategy relevance: {score}/100;" in messages[0].body
                for score in scores
            )
            assert (
                connection.execute(
                    "SELECT status FROM operational.offer_cycles WHERE id=%s",
                    (cycle_id,),
                ).fetchone()[0]
                == "confirmed"
            )
        assert (
            connection.execute(
                "SELECT state FROM operational.weekly_digest_deliveries WHERE id=%s",
                (delivery,),
            ).fetchone()[0]
            == "sent"
        )

    # A failure authorizing the second Company rolls back the first Company's
    # Sending transition, content and claims in the publication transaction.
    with psycopg.connect(url) as connection:
        owner2, _, _ = seed_digest_subscriber(
            connection, "weekly-authorization-rollback"
        )
        business2 = connection.execute(
            "SELECT id FROM operational.businesses WHERE owner_user_id=%s",
            (owner2,),
        ).fetchone()[0]
        connection.execute(
            "UPDATE operational.service_offerings SET name='Directory research',"
            "description='Understand directory records' WHERE business_id=%s",
            (business2,),
        )
        connection.execute(
            'UPDATE operational.ideal_client_profiles SET industries=\'[{"name":"SaaS"}]\','
            "company_sizes='[]',geographies='[]' WHERE business_id=%s",
            (business2,),
        )
        connection.commit()
    with PostgresProspectingUnitOfWork(factory) as work:
        PostgresDigestSubscriptionAccess(work.connection).subscribe(
            owner2, business2, now
        )
        work.commit()

    class AuthorizationFailure:
        mark_calls = 0

        class OfferCycles:
            def __init__(self, repository):
                self._repository = repository

            def __getattr__(self, name):
                return getattr(self._repository, name)

            def mark_sending(self, *args, **kwargs):
                AuthorizationFailure.mark_calls += 1
                if AuthorizationFailure.mark_calls == 2:
                    raise RuntimeError("Synthetic second-company authorization failure")
                return self._repository.mark_sending(*args, **kwargs)

        class Work:
            def __init__(self):
                self._work = PostgresProspectingUnitOfWork(factory)

            def __enter__(self):
                self._work.__enter__()
                self._work.offer_cycles = AuthorizationFailure.OfferCycles(
                    self._work.offer_cycles
                )
                return self

            def __exit__(self, *args):
                return self._work.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self._work, name)

    generation2 = RecommendationGenerationService(
        lambda: PostgresProspectingUnitOfWork(factory),
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: now + timedelta(seconds=3),
    )

    class MustNotSend:
        def send(self, message):
            raise AssertionError("Authorization failure cannot call SMTP")

    rollback_service = WeeklyDigestService(
        AuthorizationFailure.Work,
        subscription_access_factory=lambda work: PostgresDigestSubscriptionAccess(
            work.connection
        ),
        delivery_repository_factory=lambda work: PostgresWeeklyDigestDeliveryRepository(
            work.connection
        ),
        content_repository_factory=lambda work: PostgresWeeklyDigestContentRepository(
            work.connection
        ),
        source_factory=PostgresRecommendationGenerationSource,
        generation=generation2,
        renderer=base_renderer,
        sender=MustNotSend(),
        sender_address="weekly@huginn.example",
        clock=lambda: now + timedelta(seconds=3),
    )
    rollback_result = rollback_service.run()
    assert rollback_result["failed"] == 1
    assert AuthorizationFailure.mark_calls == 2
    with psycopg.connect(url) as connection:
        failed_delivery, selected_content = connection.execute(
            "SELECT id,current_content_id FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s",
            (business2,),
        ).fetchone()
        assert (
            connection.execute(
                "SELECT state FROM operational.weekly_digest_deliveries WHERE id=%s",
                (failed_delivery,),
            ).fetchone()[0]
            == "failed"
        )
        assert selected_content is None
        assert connection.execute(
            "SELECT count(*) FROM operational.weekly_digest_contents WHERE business_id=%s",
            (business2,),
        ).fetchone() == (0,)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.offer_cycles "
                "WHERE business_id=%s AND status='sending'",
                (business2,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.offer_cycle_events "
                "WHERE business_id=%s AND event_kind='sending_authorized'",
                (business2,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.offer_cycles WHERE business_id=%s",
                (business2,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.suppression_blocks "
                "WHERE business_id=%s AND kind='cooldown'",
                (business2,),
            ).fetchone()[0]
            == 0
        )

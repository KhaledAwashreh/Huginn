"""Reusable retained EU-Startups source setup for prospecting integration tests."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from xml.etree import ElementTree

import psycopg
from pytest import MonkeyPatch

from huginn.config import Config
from huginn.elt.materialization import build_eu_startups_materialization_stages
from huginn.elt.silver import signal_resolution
from huginn.management.application.read_models.generated_recommendation_reference import (
    GeneratedRecommendationReference,
)
from huginn.management.application.requests.generate_recommendations_request import (
    GenerateRecommendationsRequest,
)
from huginn.management.application.services.prospecting_read_service import (
    ProspectingReadService,
)
from huginn.management.application.services.recommendation_generation import (
    RecommendationGenerationService,
)
from huginn.management.domain.value_objects.common import Principal
from huginn.management.persistence.database.client import (
    ManagementConnectionFactory,
)
from huginn.management.persistence.database.prospecting_unit_of_work import (
    PostgresProspectingUnitOfWork,
)
from huginn.management.persistence.queries.prospecting_query import (
    PostgresProspectingQuery,
)
from huginn.management.persistence.repositories.recommendation_generation import (
    PostgresRecommendationGenerationSource,
)

_FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "eu_startups"
_HTML_FIXTURE = _FIXTURE_ROOT / "listing_brightroom.html"
_SITEMAP_FIXTURE = _FIXTURE_ROOT / "wpbdp_listing-sitemap165.xml"
_LISTING_URL = "https://www.eu-startups.com/directory/brightroom/"
_DOMAIN = "thebrightroom.de"
_STABLE_ID = "brightroom"


@dataclass(frozen=True, slots=True)
class RetainedBrightroomContext:
    database_url: str
    suffix: str
    stable_id: str
    domain: str
    listing_url: str
    account_id: UUID
    owner_user_id: UUID
    business_id: UUID
    company_id: UUID
    strategy_id: UUID
    second_strategy_id: UUID
    guard_company_id: UUID
    account_before: tuple
    user_before: tuple
    personal_profile_before: dict
    preferences_before: tuple
    configuration_before: list[tuple]
    connection_factory: ManagementConnectionFactory
    current_time: list[datetime]
    generation_service: RecommendationGenerationService
    read_service: ProspectingReadService
    principal: Principal


def seed_retained_brightroom_context(
    management_database_url: str, monkeypatch: MonkeyPatch
) -> RetainedBrightroomContext:
    """Materialize captured Brightroom source and seed an owned Business/profile.

    The source payload and sitemap last-modified value are read directly from
    retained fixtures. The returned clock is mutable for deterministic race and
    lifecycle tests; callers own all later commands and transaction assertions.
    """

    suffix = uuid4().hex
    html = _HTML_FIXTURE.read_text(encoding="utf-8")
    sitemap = ElementTree.parse(_SITEMAP_FIXTURE).getroot()
    sitemap_entry = next(
        entry for entry in sitemap if entry.findtext("{*}loc") == _LISTING_URL
    )
    captured_lastmod = sitemap_entry.findtext("{*}lastmod")
    if captured_lastmod is None:
        raise AssertionError("Captured Brightroom sitemap entry has no lastmod")
    payload = {"url": _LISTING_URL, "html": html, "lastmod": captured_lastmod}
    content_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    monkeypatch.setattr(
        signal_resolution,
        "check_domain_reachable",
        lambda checked_domain, timeout=5.0: checked_domain == _DOMAIN,
    )

    with psycopg.connect(management_database_url) as connection:
        connection.execute(
            "INSERT INTO bronze.web_scrape_ingest "
            "(source,stable_id,payload,content_hash,run_id) "
            "VALUES ('eu_startups',%s,%s,%s,%s) "
            "ON CONFLICT (source,stable_id) DO UPDATE SET "
            "payload=EXCLUDED.payload,content_hash=EXCLUDED.content_hash,"
            "run_id=EXCLUDED.run_id,fetched_at=clock_timestamp(),"
            "last_checked_at=clock_timestamp()",
            (
                _STABLE_ID,
                psycopg.types.json.Jsonb(payload),
                content_hash,
                uuid4(),
            ),
        )
    stages = build_eu_startups_materialization_stages(
        Config(database_url=management_database_url, yc_algolia_api_key="test"),
        include_manual_review=False,
        resolve_eu_startups_only=True,
    )
    counts = {stage.name: stage.run() for stage in stages}
    if counts != {
        "silver.eu_startups_staging": 1,
        "silver.signal_resolution": 1,
        "gold.company": 1,
        "gold.company_signal": 1,
        "silver.source_currentness.eu_startups": 1,
    }:
        raise AssertionError(f"Unexpected retained source materialization: {counts}")

    with psycopg.connect(management_database_url) as connection:
        account_id = connection.execute(
            "INSERT INTO operational.accounts(username,password_hash) "
            "VALUES (%s,'fixture-hash') RETURNING id",
            (f"retained-{suffix}",),
        ).fetchone()[0]
        account_before = connection.execute(
            "SELECT id,username,status FROM operational.accounts WHERE id=%s",
            (account_id,),
        ).fetchone()
        owner_user_id = connection.execute(
            "INSERT INTO operational.users "
            "(account_id,first_name,last_name,email,phone_number,country_of_residence) "
            "VALUES (%s,'F2','Tester',%s,'1','US') RETURNING id",
            (account_id, f"{suffix}@example.test"),
        ).fetchone()[0]
        user_before = connection.execute(
            "SELECT id,first_name,last_name,email,phone_number,country_of_residence "
            "FROM operational.users WHERE id=%s",
            (owner_user_id,),
        ).fetchone()
        connection.execute(
            "INSERT INTO operational.professional_profiles(user_id,headline,skills) "
            "VALUES (%s,'Independent career coach',%s)",
            (owner_user_id, psycopg.types.json.Jsonb([{"name": "coaching"}])),
        )
        personal_profile_before = connection.execute(
            "SELECT to_jsonb(profile) FROM operational.professional_profiles profile "
            "WHERE user_id=%s",
            (owner_user_id,),
        ).fetchone()[0]
        business_id = connection.execute(
            "INSERT INTO operational.businesses(owner_user_id) VALUES (%s) RETURNING id",
            (owner_user_id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO operational.business_recommendation_preferences(business_id) "
            "VALUES (%s)",
            (business_id,),
        )
        preferences_before = connection.execute(
            "SELECT business_id,repeat_interval_days,updated_at "
            "FROM operational.business_recommendation_preferences WHERE business_id=%s",
            (business_id,),
        ).fetchone()
        offering_id, icp_id = uuid4(), uuid4()
        connection.execute(
            "INSERT INTO operational.service_offerings "
            "(id,business_id,name,description) VALUES (%s,%s,%s,%s)",
            (offering_id, business_id, "Career coaching", "Coaching marketplace"),
        )
        connection.execute(
            "INSERT INTO operational.ideal_client_profiles "
            "(id,business_id,name,geographies) VALUES (%s,%s,'Germany targets',%s)",
            (
                icp_id,
                business_id,
                psycopg.types.json.Jsonb([{"kind": "country", "value": "DE"}]),
            ),
        )
        strategy_id = connection.execute(
            "INSERT INTO operational.client_discovery_strategies "
            "(business_id,name,service_offering_id,ideal_client_profile_id,is_active) "
            "VALUES (%s,'Brightroom strategy',%s,%s,true) RETURNING id",
            (business_id, offering_id, icp_id),
        ).fetchone()[0]
        second_offering_id, second_icp_id = uuid4(), uuid4()
        connection.execute(
            "INSERT INTO operational.service_offerings "
            "(id,business_id,name,description) VALUES (%s,%s,%s,%s)",
            (
                second_offering_id,
                business_id,
                "Professional coaching",
                "Career development marketplace",
            ),
        )
        connection.execute(
            "INSERT INTO operational.ideal_client_profiles "
            "(id,business_id,name,geographies) VALUES (%s,%s,'German companies',%s)",
            (
                second_icp_id,
                business_id,
                psycopg.types.json.Jsonb([{"kind": "country", "value": "Germany"}]),
            ),
        )
        second_strategy_id = connection.execute(
            "INSERT INTO operational.client_discovery_strategies "
            "(business_id,name,service_offering_id,ideal_client_profile_id,is_active) "
            "VALUES (%s,'Second Brightroom strategy',%s,%s,true) RETURNING id",
            (business_id, second_offering_id, second_icp_id),
        ).fetchone()[0]
        configuration_before = connection.execute(
            "SELECT s.id,s.service_offering_id,s.ideal_client_profile_id,o.name,o.description,"
            "i.name,i.geographies FROM operational.client_discovery_strategies s "
            "JOIN operational.service_offerings o ON o.id=s.service_offering_id "
            "JOIN operational.ideal_client_profiles i ON i.id=s.ideal_client_profile_id "
            "WHERE s.business_id=%s ORDER BY s.id",
            (business_id,),
        ).fetchall()
        company_id = connection.execute(
            "SELECT id FROM gold.company WHERE domain=%s", (_DOMAIN,)
        ).fetchone()[0]
        connection.execute(
            "UPDATE gold.company SET country='US' WHERE id=%s", (company_id,)
        )
        connection.commit()

    connection_factory = ManagementConnectionFactory(management_database_url)
    current_time = [datetime.now(UTC) + timedelta(seconds=5)]
    generation_service = RecommendationGenerationService(
        lambda: PostgresProspectingUnitOfWork(connection_factory),
        source_factory=PostgresRecommendationGenerationSource,
        clock=lambda: current_time[0],
    )
    read_service = ProspectingReadService(
        lambda: PostgresProspectingUnitOfWork(connection_factory, read_only=True),
        query_factory=lambda work: PostgresProspectingQuery(
            work, PostgresRecommendationGenerationSource(work.connection)
        ),
        clock=lambda: current_time[0],
    )
    principal = Principal(account_id, owner_user_id)
    guard_company_id = uuid4()
    with psycopg.connect(management_database_url) as connection:
        guard_company_id = connection.execute(
            "INSERT INTO gold.company(domain,name) VALUES (%s,'Currentness guard target') "
            "RETURNING id",
            (f"retained-guard-{suffix}.example.test",),
        ).fetchone()[0]
        connection.commit()

    return RetainedBrightroomContext(
        management_database_url,
        suffix,
        _STABLE_ID,
        _DOMAIN,
        _LISTING_URL,
        account_id,
        owner_user_id,
        business_id,
        company_id,
        strategy_id,
        second_strategy_id,
        guard_company_id,
        account_before,
        user_before,
        personal_profile_before,
        preferences_before,
        configuration_before,
        connection_factory,
        current_time,
        generation_service,
        read_service,
        principal,
    )


def generate_retained_brightroom_selection(
    context: RetainedBrightroomContext,
) -> GeneratedRecommendationReference:
    """Generate and return Brightroom's exact current selected revision."""

    with psycopg.connect(context.database_url) as connection:
        connection.execute(
            "UPDATE gold.company SET country=NULL WHERE id=%s",
            (context.company_id,),
        )
        connection.commit()
    generated = context.generation_service.execute(
        context.principal,
        GenerateRecommendationsRequest(context.strategy_id),
    )
    with PostgresProspectingUnitOfWork(
        context.connection_factory, read_only=True
    ) as work:
        recommendation = work.recommendations.get_open(
            context.business_id, context.company_id
        )
    if recommendation is None:
        raise AssertionError("Retained Brightroom was not selected")
    selection = next(
        (
            reference
            for reference in generated.references
            if reference.recommendation_id == recommendation.id
            and reference.revision_id == recommendation.current_revision_id
        ),
        None,
    )
    if selection is None:
        raise AssertionError("Retained Brightroom has no reference in this run")
    return selection

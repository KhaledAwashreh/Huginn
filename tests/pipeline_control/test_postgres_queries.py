from datetime import UTC, datetime
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.pipeline_control.application.requests.list_invocation_companies_request import (
    ListInvocationCompaniesRequest,
)
from huginn.pipeline_control.application.services.list_invocation_companies_service import (
    ListInvocationCompaniesService,
)
from huginn.pipeline_control.domain.value_objects.stage_plan import SUPPORTED_STAGE_PLAN
from huginn.pipeline_control.persistence.queries.invocation_company_reader import (
    PostgresInvocationCompanyReader,
)
from huginn.pipeline_control.persistence.queries.invocation_reader import (
    PostgresInvocationReader,
)


def test_bounded_company_results_and_detail_metrics_are_invocation_scoped(
    integration_database_url: str,
) -> None:
    now = datetime.now(UTC)
    account_id, invocation_id, other_invocation_id, tracked_other_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    ingestion_job_id, source_job_id, gold_job_id, other_gold_job_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    companies = [
        (uuid4(), f"{uuid4().hex}.example.test"),
        (uuid4(), f"{uuid4().hex}.example.test"),
    ]
    other_company = (uuid4(), f"{uuid4().hex}.example.test")
    with psycopg.connect(integration_database_url) as connection:
        connection.execute(
            "INSERT INTO operational.accounts (id, username, password_hash) VALUES (%s, %s, 'hash')",
            (account_id, f"pipeline-reader-{account_id}"),
        )
        for invocation, request_id, tracking_state in (
            (invocation_id, uuid4(), "tracked"),
            (other_invocation_id, uuid4(), "unknown_legacy"),
            (tracked_other_id, uuid4(), "tracked"),
        ):
            connection.execute(
                "INSERT INTO ops.pipeline_invocations "
                "(id, requester_account_id, request_id, state, requested_at, plan, company_results_tracking_state) "
                "VALUES (%s, %s, %s, 'succeeded', %s, %s, %s)",
                (
                    invocation,
                    account_id,
                    request_id,
                    now,
                    Jsonb(SUPPORTED_STAGE_PLAN.to_json()),
                    tracking_state,
                ),
            )
        connection.execute(
            "INSERT INTO ops.job_runs (id, source, status, rows_written, invocation_id, execution_kind) "
            "VALUES (%s, 'ingestion', 'succeeded', 2, %s, 'stage'), (%s, 'gold.company', 'succeeded', 2, %s, 'stage')",
            (ingestion_job_id, invocation_id, gold_job_id, invocation_id),
        )
        connection.execute(
            "INSERT INTO ops.job_runs (id, source, status, rows_written, invocation_id, parent_job_run_id, execution_kind) "
            "VALUES (%s, 'hn', 'failed', 0, %s, %s, 'source')",
            (source_job_id, invocation_id, ingestion_job_id),
        )
        connection.execute(
            "INSERT INTO ops.job_runs (id, source, status, rows_written, invocation_id, execution_kind) "
            "VALUES (%s, 'gold.company', 'succeeded', 1, %s, 'stage')",
            (other_gold_job_id, tracked_other_id),
        )
        for company_id, domain in companies:
            connection.execute(
                "INSERT INTO gold.company (id, domain, name, business_sector, country, company_scale, company_status, email, notes) "
                "VALUES (%s, %s, 'Private Test Co', ARRAY['Software'], 'US', '0-10', 'Active', 'private@example.test', 'private note')",
                (company_id, domain),
            )
            connection.execute(
                "INSERT INTO ops.pipeline_company_results (invocation_id, company_id, stage_job_run_id) VALUES (%s, %s, %s)",
                (invocation_id, company_id, gold_job_id),
            )
        connection.execute(
            "INSERT INTO gold.company (id, domain, name) VALUES (%s, %s, 'Other Invocation Co')",
            other_company,
        )
        connection.execute(
            "INSERT INTO ops.pipeline_company_results (invocation_id, company_id, stage_job_run_id) VALUES (%s, %s, %s)",
            (tracked_other_id, other_company[0], other_gold_job_id),
        )
    factory = ManagementConnectionFactory(integration_database_url)
    company_reader = PostgresInvocationCompanyReader(factory)
    service = ListInvocationCompaniesService(company_reader)
    first_page = service.execute(ListInvocationCompaniesRequest(invocation_id, 1, 0))
    second_page = service.execute(ListInvocationCompaniesRequest(invocation_id, 1, 1))
    legacy_page = service.execute(
        ListInvocationCompaniesRequest(other_invocation_id, 10, 0)
    )
    isolated_page = service.execute(
        ListInvocationCompaniesRequest(tracked_other_id, 10, 0)
    )

    assert first_page.tracking_state == "tracked"
    assert first_page.total_count == 2 and first_page.has_more
    assert second_page.total_count == 2 and not second_page.has_more
    assert first_page.items[0].id < second_page.items[0].id
    assert first_page.items[0].stage_job_run_id == gold_job_id
    assert set(vars(first_page.items[0])) == {
        "id",
        "name",
        "domain",
        "business_sector",
        "country",
        "company_scale",
        "company_status",
        "stage_job_run_id",
    }
    assert legacy_page.tracking_state == "unknown_legacy"
    assert legacy_page.items == () and legacy_page.total_count == 0
    assert isolated_page.total_count == 1
    assert [company.id for company in isolated_page.items] == [other_company[0]]

    detail = PostgresInvocationReader(factory, clock=lambda: now).get(invocation_id)
    assert detail is not None
    aggregate = next(stage for stage in detail.stages if stage.name == "ingestion")
    assert [
        (metric.kind, metric.unit, metric.value) for metric in aggregate.metrics
    ] == [("failed_sources", "sources", 2)]
    assert detail.sources[0].name == "hn"
    assert detail.sources[0].parent_job_run_id == ingestion_job_id

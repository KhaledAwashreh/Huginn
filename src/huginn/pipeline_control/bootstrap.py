"""Lazy composition for pipeline admission and read-only administration."""

from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace

from huginn.config import Config
from huginn.elt.__main__ import build_stages
from huginn.management.persistence.database.client import ManagementConnectionFactory
from huginn.pipeline_control.application.services.get_invocation_service import (
    GetInvocationService,
)
from huginn.pipeline_control.application.services.list_events_service import (
    ListEventsService,
)
from huginn.pipeline_control.application.services.list_invocation_companies_service import (
    ListInvocationCompaniesService,
)
from huginn.pipeline_control.application.services.list_invocations_service import (
    ListInvocationsService,
)
from huginn.pipeline_control.application.services.trigger_invocation_service import (
    TriggerInvocationService,
)
from huginn.pipeline_control.domain.value_objects.stage_descriptor import (
    StageDescriptor,
)
from huginn.pipeline_control.domain.value_objects.stage_plan import (
    SUPPORTED_STAGE_PLAN,
    StagePlan,
)
from huginn.pipeline_control.persistence.database.unit_of_work import (
    PostgresPipelineUnitOfWork,
)
from huginn.pipeline_control.persistence.queries.invocation_company_reader import (
    PostgresInvocationCompanyReader,
)
from huginn.pipeline_control.persistence.queries.invocation_reader import (
    PostgresInvocationReader,
)


def create_pipeline_services(
    database_url: str, *, clock: Callable[[], datetime] | None = None
) -> SimpleNamespace:
    """Build services without constructing an adapter or connecting to PostgreSQL."""

    def make_connection():
        return ManagementConnectionFactory(
            database_url, statement_timeout_ms=2_000
        ).connect()

    stages = build_stages(Config(database_url=database_url, yc_algolia_api_key=""))
    expected = {stage.name: stage for stage in SUPPORTED_STAGE_PLAN.stages}
    plan = StagePlan(
        tuple(
            StageDescriptor(
                stage.name,
                order,
                stage.depends_on,
                expected[stage.name].group,
                expected[stage.name].source_children,
            )
            for order, stage in enumerate(stages)
        )
    )
    if plan != SUPPORTED_STAGE_PLAN:
        raise ValueError("pipeline stage graph differs from the supported plan")
    factory = SimpleNamespace(connect=make_connection)
    reader = PostgresInvocationReader(factory, clock=clock)
    companies = PostgresInvocationCompanyReader(factory)
    return SimpleNamespace(
        trigger=TriggerInvocationService(
            lambda: PostgresPipelineUnitOfWork(factory), plan, clock=clock
        ),
        get=GetInvocationService(reader),
        history=ListInvocationsService(reader),
        events=ListEventsService(reader),
        companies=ListInvocationCompaniesService(companies),
    )

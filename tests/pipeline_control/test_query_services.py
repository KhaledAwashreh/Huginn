from datetime import UTC, datetime
from uuid import UUID

import pytest

from huginn.pipeline_control.application.errors.invocation import (
    InvocationNotFoundError,
)
from huginn.pipeline_control.application.read_models.event_entry import EventEntry
from huginn.pipeline_control.application.read_models.invocation_company_result import (
    InvocationCompanyResult,
)
from huginn.pipeline_control.application.read_models.invocation_summary import (
    InvocationSummary,
)
from huginn.pipeline_control.application.requests.get_invocation_request import (
    GetInvocationRequest,
)
from huginn.pipeline_control.application.requests.list_events_request import (
    ListEventsRequest,
)
from huginn.pipeline_control.application.requests.list_invocation_companies_request import (
    ListInvocationCompaniesRequest,
)
from huginn.pipeline_control.application.requests.list_invocations_request import (
    ListInvocationsRequest,
)
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
from huginn.pipeline_control.domain.value_objects.stage_plan import SUPPORTED_STAGE_PLAN
from huginn.pipeline_control.persistence.queries.invocation_reader import _detail

NOW = datetime(2026, 10, 9, tzinfo=UTC)
INVOCATION_ID = UUID("00000000-0000-0000-0000-000000000010")


class _Reader:
    def __init__(self):
        self.items = tuple(
            InvocationSummary(
                UUID(int=i), UUID(int=1), "succeeded", NOW, None, NOW, None
            )
            for i in range(1, 4)
        )
        self.event_items = tuple(
            EventEntry(
                UUID(int=i),
                i,
                NOW,
                "stage_succeeded",
                None,
                None,
                "gold.company",
                None,
                (),
            )
            for i in range(1, 4)
        )

    def get(self, invocation_id):
        return object() if invocation_id == INVOCATION_ID else None

    def list(self, limit, offset, _state):
        return self.items[offset : offset + limit]

    def events(self, _invocation_id, after, limit):
        return tuple(event for event in self.event_items if event.sequence > after)[
            :limit
        ]


class _CompanyReader:
    def read(self, _invocation_id, limit, offset):
        item = InvocationCompanyResult(
            UUID(int=4),
            "Company",
            "example.test",
            ("Software",),
            "US",
            "0-10",
            "Active",
            UUID(int=5),
        )
        return "tracked", (item,)[offset : offset + limit], 1


def test_invocation_history_pages_are_bounded_and_newest_reader_order_is_retained():
    response = ListInvocationsService(_Reader()).execute(ListInvocationsRequest(2, 0))
    assert len(response.items) == 2
    assert response.has_more


def test_events_use_exclusive_monotonic_cursor_and_limit_plus_one():
    response = ListEventsService(_Reader()).execute(
        ListEventsRequest(INVOCATION_ID, 0, 2)
    )
    assert [event.sequence for event in response.items] == [1, 2]
    assert response.next_after_sequence == 2
    assert response.has_more


def test_private_invocation_queries_return_not_found():
    with pytest.raises(InvocationNotFoundError):
        GetInvocationService(_Reader()).execute(GetInvocationRequest(UUID(int=9)))
    with pytest.raises(InvocationNotFoundError):
        ListEventsService(_Reader()).execute(ListEventsRequest(UUID(int=9), 0, 10))


def test_company_results_service_enforces_maximum_page_size():
    service = ListInvocationCompaniesService(_CompanyReader())
    assert (
        service.execute(ListInvocationCompaniesRequest(INVOCATION_ID, 100, 0)).has_more
        is False
    )
    with pytest.raises(ValueError):
        service.execute(ListInvocationCompaniesRequest(INVOCATION_ID, 101, 0))


def test_detail_uses_typed_aggregate_metric_and_safe_event_outcomes_only():
    ingestion_id, source_id, skipped_id = UUID(int=20), UUID(int=21), UUID(int=22)
    row = (
        INVOCATION_ID,
        UUID(int=1),
        UUID(int=2),
        "failed",
        NOW,
        NOW,
        NOW,
        NOW,
        SUPPORTED_STAGE_PLAN.to_json(),
        "ingestion_failed",
        "tracked",
    )
    jobs = [
        (
            ingestion_id,
            "ingestion",
            NOW,
            NOW,
            "failed",
            2,
            "DSN password=secret",
            None,
            "stage",
        ),
        (
            source_id,
            "hn",
            NOW,
            NOW,
            "failed",
            0,
            "raw credential text",
            ingestion_id,
            "source",
        ),
        (
            skipped_id,
            "silver.hn_staging",
            NOW,
            NOW,
            "skipped",
            0,
            "unsafe detail",
            None,
            "stage",
        ),
    ]
    events = [
        (
            "stage_failed",
            "ingestion",
            None,
            "ingestion_failed",
            "Source ingestion failed",
        ),
        ("source_failed", None, "hn", "source_unavailable", "Source request failed"),
        (
            "stage_skipped",
            "silver.hn_staging",
            None,
            None,
            "Dependency ingestion failed",
        ),
    ]
    detail = _detail(row, jobs, events, NOW)

    assert [(metric.kind, metric.value) for metric in detail.stages[0].metrics] == [
        ("failed_sources", None)
    ]
    assert detail.stages[0].safe_error_code == "ingestion_failed"
    assert detail.stages[2].skip_reason == "Dependency ingestion failed"
    assert detail.sources[0].safe_error_code == "source_unavailable"
    assert "secret" not in repr(detail)
    assert "credential" not in repr(detail)

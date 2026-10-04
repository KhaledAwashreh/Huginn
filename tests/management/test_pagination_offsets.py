from uuid import uuid4

import pytest

from huginn.management.application.services.discovery_strategies import (
    ClientDiscoveryStrategyService,
)
from huginn.management.application.services.ideal_client_profiles import (
    IdealClientProfileService,
)
from huginn.management.application.services.service_offerings import (
    ServiceOfferingService,
)
from huginn.management.domain.value_objects.common import Principal

TOO_LARGE_OFFSET = 9_223_372_036_854_775_808


def fail_if_called():
    pytest.fail("a page beyond PostgreSQL's bigint range must not query storage")


@pytest.mark.parametrize(
    ("service_type", "list_kwargs"),
    [
        (ServiceOfferingService, {}),
        (IdealClientProfileService, {}),
        (ClientDiscoveryStrategyService, {"active": None}),
    ],
)
def test_list_services_return_empty_page_before_repository_query(
    service_type, list_kwargs
):
    factories = {
        ServiceOfferingService: {"offerings_factory": lambda _uow: fail_if_called()},
        IdealClientProfileService: {"profiles_factory": lambda _uow: fail_if_called()},
        ClientDiscoveryStrategyService: {
            "strategies_factory": lambda _uow: fail_if_called(),
            "offerings_factory": lambda _uow: fail_if_called(),
            "profiles_factory": lambda _uow: fail_if_called(),
        },
    }[service_type]
    service = service_type(fail_if_called, **factories)

    page = service.list(
        Principal(uuid4(), uuid4()),
        limit=50,
        offset=TOO_LARGE_OFFSET,
        **list_kwargs,
    )

    assert page.items == ()
    assert (page.offset, page.limit, page.has_more) == (TOO_LARGE_OFFSET, 50, False)

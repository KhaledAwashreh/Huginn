from huginn.management.repositories.postgres.discovery_strategy import (
    PostgresClientDiscoveryStrategyRepository,
)
from huginn.management.repositories.postgres.ideal_client_profile import (
    PostgresIdealClientProfileRepository,
)
from huginn.management.repositories.postgres.service_offering import (
    PostgresServiceOfferingRepository,
)


def test_resource_postgres_implementations_live_in_resource_modules():
    assert PostgresServiceOfferingRepository.__module__.endswith(
        ".repositories.postgres.service_offering"
    )
    assert PostgresIdealClientProfileRepository.__module__.endswith(
        ".repositories.postgres.ideal_client_profile"
    )
    assert PostgresClientDiscoveryStrategyRepository.__module__.endswith(
        ".repositories.postgres.discovery_strategy"
    )

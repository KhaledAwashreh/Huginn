"""Current User-owned configuration queries, design section 2."""

from uuid import UUID

from psycopg import Connection

from huginn.matchmaking.application.read_models.strategy_configuration import (
    StrategyConfiguration,
)
from huginn.matchmaking.application.read_models.user_availability import (
    UserAvailability,
)
from huginn.matchmaking.persistence.row_models.strategy_configuration import (
    StrategyConfigurationRow,
)
from huginn.matchmaking.persistence.row_models.user_availability import (
    UserAvailabilityRow,
)


class SqlConfigurationRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def user_availability(self, user_id: UUID) -> UserAvailability:
        row = self._connection.execute(
            """
            SELECT u.id AS user_id, a.id AS account_id, a.status AS account_status
            FROM operational.users AS u
            LEFT JOIN operational.accounts AS a ON a.id = u.account_id
            WHERE u.id = %s;
        """,
            (user_id,),
        ).fetchone()
        if row is None:
            return UserAvailability.MISSING
        return UserAvailabilityRow(*row).to_read_model()

    def list_active_strategies(
        self, user_id: UUID
    ) -> tuple[StrategyConfiguration, ...]:
        rows = self._connection.execute(
            """
            SELECT s.id AS strategy_id, s.user_id, s.name, s.service_offering_id,
                   s.ideal_client_profile_id AS icp_id,
                   o.id AS offering_row_id, p.id AS icp_row_id,
                   p.industries, p.company_sizes, p.geographies, p.exclusions
            FROM operational.client_discovery_strategies AS s
            LEFT JOIN operational.service_offerings AS o
              ON o.user_id = s.user_id AND o.id = s.service_offering_id
            LEFT JOIN operational.ideal_client_profiles AS p
              ON p.user_id = s.user_id AND p.id = s.ideal_client_profile_id
            WHERE s.user_id = %s AND s.is_active IS TRUE
            ORDER BY s.id ASC;
        """,
            (user_id,),
        ).fetchall()
        return tuple(StrategyConfigurationRow(*row).to_read_model() for row in rows)

from uuid import UUID

from huginn.management.domain.value_objects.common import Page
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.matchmaking_control.application.read_models.target_user import TargetUser


class PostgresTargetUserQuery:
    def __init__(self, connection: DatabaseSession) -> None:
        self._connection = connection
        self._eligible_count = 0

    def search(self, search: str, offset: int, limit: int) -> Page[TargetUser]:
        normalized = search.strip()
        try:
            query_id = UUID(normalized)
        except ValueError:
            filter_sql = "position(lower(%s) in lower(btrim(u.first_name) || ' ' || btrim(u.last_name)))>0"
            filter_value = normalized
        else:
            filter_sql = "u.id=%s"
            filter_value = query_id
        rows = self._connection.execute(
            "SELECT eligible.total,page.id,page.first_name,page.last_name,page.has_active_strategies "
            "FROM (SELECT count(*) AS total FROM operational.users eu JOIN operational.accounts ea ON ea.id=eu.account_id "
            "WHERE ea.status='active' AND EXISTS (SELECT 1 FROM operational.client_discovery_strategies es JOIN operational.businesses eb ON eb.id=es.business_id WHERE eb.owner_user_id=eu.id AND es.is_active)) eligible "
            "LEFT JOIN LATERAL (SELECT u.id,u.first_name,u.last_name,EXISTS (SELECT 1 FROM operational.client_discovery_strategies s JOIN operational.businesses b ON b.id=s.business_id WHERE b.owner_user_id=u.id AND s.is_active) AS has_active_strategies "
            "FROM operational.users u JOIN operational.accounts a ON a.id=u.account_id WHERE a.status='active' AND "
            + filter_sql
            + " ORDER BY lower(u.first_name),lower(u.last_name),u.id LIMIT %s OFFSET %s) page ON TRUE",
            (filter_value, limit + 1, offset),
        ).fetchall()
        self._eligible_count = rows[0][0] if rows else 0
        users = tuple(
            TargetUser(
                id=row[1],
                first_name=row[2],
                last_name=row[3],
                has_active_strategies=row[4],
            )
            for row in rows
            if row[1] is not None
        )
        return Page(
            items=users[:limit], limit=limit, offset=offset, has_more=len(users) > limit
        )

    def eligible_count(self) -> int:
        return self._eligible_count

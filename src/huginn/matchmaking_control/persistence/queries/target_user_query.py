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
        is_uuid = False
        try:
            query_id = UUID(normalized)
            is_uuid = True
        except ValueError:
            query_id = None
        filter_sql = (
            "u.id=%s"
            if is_uuid
            else "(%s='' OR position(lower(%s) in lower(a.username))>0 OR position(lower(%s) in lower(u.first_name || ' ' || u.last_name))>0)"
        )
        filter_params = (query_id,) if is_uuid else (normalized, normalized, normalized)
        rows = self._connection.execute(
            "SELECT eligible.total,page.id,page.username,page.first_name,page.last_name,page.has_active_strategies "
            "FROM (SELECT count(*) AS total FROM operational.users eu JOIN operational.accounts ea ON ea.id=eu.account_id "
            "WHERE ea.status='active' AND EXISTS (SELECT 1 FROM operational.client_discovery_strategies es WHERE es.user_id=eu.id AND es.is_active)) eligible "
            "LEFT JOIN LATERAL (SELECT u.id,a.username,u.first_name,u.last_name,EXISTS (SELECT 1 FROM operational.client_discovery_strategies s WHERE s.user_id=u.id AND s.is_active) AS has_active_strategies "
            "FROM operational.users u JOIN operational.accounts a ON a.id=u.account_id WHERE a.status='active' AND "
            + filter_sql
            + " ORDER BY a.username,u.id LIMIT %s OFFSET %s) page ON TRUE",
            (*filter_params, limit + 1, offset),
        ).fetchall()
        self._eligible_count = rows[0][0] if rows else 0
        users = tuple(
            TargetUser(
                id=row[1],
                username=row[2],
                first_name=row[3],
                last_name=row[4],
                has_active_strategies=row[5],
            )
            for row in rows
            if row[1] is not None
        )
        return Page(
            items=users[:limit], limit=limit, offset=offset, has_more=len(users) > limit
        )

    def eligible_count(self) -> int:
        return self._eligible_count

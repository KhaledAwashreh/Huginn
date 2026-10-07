"""Creation-only durable Match write, design section 7."""

from uuid import UUID

from psycopg import Connection

from huginn.matchmaking.domain.entities.match import Match
from huginn.matchmaking.persistence.row_models.match import MatchRow


class SqlMatchRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def insert_if_absent(self, user_id: UUID, company_id: UUID) -> Match | None:
        row = self._connection.execute(
            """
            INSERT INTO operational.match (user_id, company_id, status, notes)
            VALUES (%s, %s, 'new', NULL)
            ON CONFLICT (user_id, company_id) DO NOTHING
            RETURNING id, user_id, company_id, status, notes, created_at, updated_at;
        """,
            (user_id, company_id),
        ).fetchone()
        return None if row is None else MatchRow(*row).to_domain()

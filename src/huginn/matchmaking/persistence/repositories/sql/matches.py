"""Creation-only durable Match write, design section 7."""

from uuid import UUID

from psycopg import Connection

from huginn.matchmaking.domain.entities.match import Match
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow
from huginn.matchmaking.persistence.errors.database import DataIntegrityError
from huginn.matchmaking.persistence.row_models.match import MatchRow


class SqlMatchRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def insert_if_absent(
        self,
        user_id: UUID,
        company_id: UUID,
        *,
        observation_ids: tuple[UUID, ...],
        window: SignalWindow,
    ) -> Match | None:
        if (
            not isinstance(observation_ids, tuple)
            or not observation_ids
            or any(not isinstance(item, UUID) for item in observation_ids)
            or len(set(observation_ids)) != len(observation_ids)
            or not isinstance(window, SignalWindow)
        ):
            raise DataIntegrityError("Invalid Match source evidence")
        if self._connection.autocommit:
            raise DataIntegrityError("Match evidence requires a transaction")
        row = self._connection.execute(
            """
            INSERT INTO operational.match (user_id, company_id, status, notes)
            VALUES (%s, %s, 'new', NULL)
            ON CONFLICT (user_id, company_id) DO NOTHING
            RETURNING id, user_id, company_id, status, notes, created_at, updated_at;
        """,
            (user_id, company_id),
        ).fetchone()
        if row is None:
            return None
        match = MatchRow(*row).to_domain()
        self._connection.execute(
            """
            INSERT INTO operational.match_source_evidence
                (match_id, observation_id, cutoff, as_of)
            SELECT %s, evidence.observation_id, %s, %s
            FROM unnest(%s::uuid[]) AS evidence(observation_id)
            ORDER BY evidence.observation_id;
            """,
            (match.id, window.cutoff, window.as_of, list(observation_ids)),
        )
        return match

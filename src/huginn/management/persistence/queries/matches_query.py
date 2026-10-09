"""Parameterized owner-scoped reads for the Matches workspace."""

from uuid import UUID

from huginn.management.application.read_models.current_company import CurrentCompany
from huginn.management.application.read_models.current_company_signal import (
    CurrentCompanySignal,
)
from huginn.management.application.read_models.evaluation_summary import (
    EvaluationSummary,
)
from huginn.management.application.read_models.matches_overview import MatchesOverview
from huginn.management.application.read_models.user_match import UserMatch
from huginn.management.domain.value_objects.common import Page
from huginn.management.domain.value_objects.match_status import MatchStatus
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.row_models.current_company import CurrentCompanyRow
from huginn.management.persistence.row_models.current_company_signal import (
    CurrentCompanySignalRow,
)
from huginn.management.persistence.row_models.evaluation_summary import (
    EvaluationSummaryRow,
)
from huginn.management.persistence.row_models.matches_overview import MatchesOverviewRow
from huginn.management.persistence.row_models.user_match import UserMatchRow


class PostgresMatchesQuery:
    def __init__(self, connection: DatabaseSession) -> None:
        self._connection = connection

    @staticmethod
    def _match(row: tuple[object, ...]) -> UserMatch:
        value = UserMatchRow(
            id=row[0],
            user_id=row[1],
            status=row[2],
            notes=row[3],
            created_at=row[4],
            updated_at=row[5],
            company_id=row[6],
            company_name=row[7],
            company_domain=row[8],
            business_sector=row[9],
            country=row[10],
            company_scale=row[11],
            company_status=row[12],
        )
        company_value = CurrentCompanyRow(
            id=value.company_id,
            name=value.company_name,
            domain=value.company_domain,
            business_sector=value.business_sector,
            country=value.country,
            company_scale=value.company_scale,
            company_status=value.company_status,
        )
        company = CurrentCompany(
            company_value.id,
            company_value.name,
            company_value.domain,
            None
            if company_value.business_sector is None
            else tuple(company_value.business_sector),
            company_value.country,
            company_value.company_scale,
            company_value.company_status,
        )
        return UserMatch(
            value.id,
            value.user_id,
            MatchStatus(value.status),
            value.notes,
            value.created_at,
            value.updated_at,
            company,
        )

    def list_matches(
        self, user_id: UUID, status: MatchStatus | None, offset: int, limit: int
    ) -> Page[UserMatch]:
        where = "m.user_id=%s"
        parameters: tuple[object, ...]
        if status is None:
            parameters = (user_id, limit + 1, offset)
        else:
            where += " AND m.status=%s"
            parameters = (user_id, status.value, limit + 1, offset)
        rows = self._connection.execute(
            f"""SELECT m.id,m.user_id,m.status,m.notes,m.created_at,m.updated_at,
                       c.id,c.name,c.domain,c.business_sector,c.country,
                       c.company_scale,c.company_status
                FROM operational.match AS m
                JOIN gold.company AS c ON c.id=m.company_id
                WHERE {where}
                ORDER BY m.created_at DESC,m.id DESC LIMIT %s OFFSET %s""",
            parameters,
        ).fetchall()
        return Page(
            tuple(self._match(row) for row in rows[:limit]),
            offset,
            limit,
            len(rows) > limit,
        )

    def get_match(self, user_id: UUID, match_id: UUID) -> UserMatch | None:
        row = self._connection.execute(
            """SELECT m.id,m.user_id,m.status,m.notes,m.created_at,m.updated_at,
                      c.id,c.name,c.domain,c.business_sector,c.country,
                      c.company_scale,c.company_status
               FROM operational.match AS m JOIN gold.company AS c ON c.id=m.company_id
               WHERE m.user_id=%s AND m.id=%s""",
            (user_id, match_id),
        ).fetchone()
        return None if row is None else self._match(row)

    def list_match_signals(
        self, user_id: UUID, match_id: UUID, offset: int, limit: int
    ) -> Page[CurrentCompanySignal]:
        rows = self._connection.execute(
            """SELECT s.id,s.signal_type,s.source,s.source_url,s.description,
                      s.stage,s.occurred_at,s.ingested_at
               FROM operational.match AS m
               JOIN gold.company_signal AS s ON s.company_id=m.company_id
               WHERE m.user_id=%s AND m.id=%s
               ORDER BY s.occurred_at DESC,s.id DESC LIMIT %s OFFSET %s""",
            (user_id, match_id, limit + 1, offset),
        ).fetchall()
        items = tuple(
            CurrentCompanySignal(
                value.id,
                value.signal_type,
                value.source,
                value.source_url,
                value.description,
                value.stage,
                value.occurred_at,
                value.ingested_at,
            )
            for row in rows[:limit]
            for value in [
                CurrentCompanySignalRow(
                    id=row[0],
                    signal_type=row[1],
                    source=row[2],
                    source_url=row[3],
                    description=row[4],
                    stage=row[5],
                    occurred_at=row[6],
                    ingested_at=row[7],
                )
            ]
        )
        return Page(items, offset, limit, len(rows) > limit)

    def overview_for(self, user_id: UUID) -> MatchesOverview:
        row = self._connection.execute(
            """SELECT EXISTS(SELECT 1 FROM operational.match WHERE user_id=%s),
                      EXISTS(SELECT 1 FROM operational.client_discovery_strategies
                             WHERE user_id=%s AND is_active),
                      latest.state,latest.requested_at,latest.started_at,latest.finished_at,
                      latest.cutoff,latest.as_of,latest.tracking_stale,
                      latest.strategies_evaluated,latest.strategies_skipped,
                      latest.created_matches_count,latest.existing_matches_skipped_count
               FROM (SELECT 1) AS seed
               LEFT JOIN LATERAL (
                   SELECT u.state,r.requested_at,u.started_at,u.finished_at,r.cutoff,r.as_of,
                          (r.state='running' AND u.state IN ('pending','running')
                           AND (r.heartbeat_at IS NULL OR
                           r.heartbeat_at < now() - interval '60 seconds')) AS tracking_stale,
                          u.strategies_evaluated,u.strategies_skipped,
                          u.created_matches_count,u.existing_matches_skipped_count
                   FROM ops.matchmaking_run_users AS u
                   JOIN ops.matchmaking_runs AS r ON r.id=u.run_id
                   WHERE u.user_id=%s
                   ORDER BY r.requested_at DESC,r.id DESC LIMIT 1
               ) AS latest ON TRUE""",
            (user_id, user_id, user_id),
        ).fetchone()
        # Normalize the database boundary into strict rows before mapping.
        if row is None:
            raise RuntimeError("overview query returned no row")
        overview_row = MatchesOverviewRow(
            has_matches=row[0], has_active_strategies=row[1]
        )
        if row[2] is None:
            latest = None
        else:
            state = row[2]
            stale = row[8]
            counts = state == "succeeded"
            latest_row = EvaluationSummaryRow(
                state=state,
                requested_at=row[3],
                started_at=row[4],
                finished_at=row[5],
                cutoff=row[6],
                as_of=row[7],
                tracking_stale=stale,
                strategies_evaluated=row[9] if counts else None,
                strategies_skipped=row[10] if counts else None,
                created_matches_count=row[11] if counts else None,
                existing_matches_skipped_count=row[12] if counts else None,
            )
            latest = EvaluationSummary(**latest_row.model_dump())
        return MatchesOverview(
            overview_row.has_matches, overview_row.has_active_strategies, latest
        )

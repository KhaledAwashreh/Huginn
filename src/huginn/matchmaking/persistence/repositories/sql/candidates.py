"""Static bound Gold eligibility query, design section 6."""

from psycopg import Connection

from huginn.matchmaking.application.read_models.company_candidate import (
    CompanyCandidate,
)
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow
from huginn.matchmaking.persistence.row_models.company_candidate import (
    CompanyCandidateRow,
)


class SqlCandidateRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def find_candidates(
        self, criteria: CompiledCriteria, window: SignalWindow
    ) -> tuple[CompanyCandidate, ...]:
        rows = self._connection.execute(
            """
            WITH target AS (
                SELECT
                  ARRAY(SELECT lower(btrim(v)) FROM unnest(%s::text[]) AS t(v)) AS industries,
                  %s::text[] AS company_sizes,
                  ARRAY(SELECT lower(btrim(v)) FROM unnest(%s::text[]) AS t(v)) AS countries,
                  %s::uuid[] AS excluded_company_ids,
                  ARRAY(SELECT lower(btrim(v)) FROM unnest(%s::text[]) AS t(v)) AS excluded_industries,
                  ARRAY(SELECT lower(btrim(v)) FROM unnest(%s::text[]) AS t(v)) AS excluded_countries
            )
            SELECT c.id AS company_id
            FROM gold.company AS c
            CROSS JOIN target AS t
            WHERE EXISTS (
                SELECT 1 FROM unnest(c.business_sector) AS sector(value)
                WHERE sector.value IS NOT NULL
                  AND btrim(sector.value) <> ''
                  AND lower(btrim(sector.value)) <> 'unspecified'
                  AND lower(btrim(sector.value)) = ANY(t.industries)
            )
              AND c.company_scale = ANY(t.company_sizes)
              AND c.country IS NOT NULL AND btrim(c.country) <> ''
              AND lower(btrim(c.country)) = ANY(t.countries)
              AND NOT (c.id = ANY(t.excluded_company_ids))
              AND NOT EXISTS (
                SELECT 1 FROM unnest(c.business_sector) AS sector(value)
                WHERE sector.value IS NOT NULL
                  AND btrim(sector.value) <> ''
                  AND lower(btrim(sector.value)) <> 'unspecified'
                  AND lower(btrim(sector.value)) = ANY(t.excluded_industries)
              )
              AND NOT (lower(btrim(c.country)) = ANY(t.excluded_countries))
              AND EXISTS (
                SELECT 1 FROM gold.company_signal AS signal
                WHERE signal.company_id = c.id
                  AND signal.occurred_at >= %s::timestamptz
                  AND signal.occurred_at <= %s::timestamptz
              )
            ORDER BY c.id ASC;
        """,
            (
                list(criteria.industries),
                list(criteria.company_sizes),
                list(criteria.countries),
                list(criteria.excluded_company_ids),
                list(criteria.excluded_industries),
                list(criteria.excluded_countries),
                window.cutoff,
                window.as_of,
            ),
        ).fetchall()
        return tuple(CompanyCandidateRow(*row).to_read_model() for row in rows)

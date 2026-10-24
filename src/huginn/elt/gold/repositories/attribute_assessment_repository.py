"""Read-only PostgreSQL adapter for attribute promotion assessments."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from huginn.elt.gold.models.assessment_snapshot import AssessmentSnapshot
from huginn.elt.gold.models.company_attributes import CompanyAttributes
from huginn.elt.gold.models.source_fact import SourceFact
from huginn.elt.gold.repositories.protocols.attribute_assessment_repository import (
    AttributeAssessmentRepository,
)
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow

_DEFAULT_STATEMENT_TIMEOUT_MS = 30_000
_MAX_STATEMENT_TIMEOUT_MS = 600_000


class PostgresAssessmentRepository(AttributeAssessmentRepository):
    """Read guarded current evidence under one bounded, read-only snapshot."""

    def __init__(
        self,
        database_url: str,
        statement_timeout_ms: int = _DEFAULT_STATEMENT_TIMEOUT_MS,
        *,
        connect: Callable[..., object] | None = None,
    ) -> None:
        if (
            isinstance(statement_timeout_ms, bool)
            or not isinstance(statement_timeout_ms, int)
            or not 0 < statement_timeout_ms <= _MAX_STATEMENT_TIMEOUT_MS
        ):
            raise ValueError(
                "statement_timeout_ms must be an integer from 1 through "
                f"{_MAX_STATEMENT_TIMEOUT_MS}"
            )
        self._database_url = database_url
        self._statement_timeout_ms = statement_timeout_ms
        self._connect = connect

    def _connection(self):
        if self._connect is None:
            return psycopg.connect(self._database_url, connect_timeout=5)
        return self._connect(self._database_url)

    def read_snapshot(self, limit: int | None = None) -> AssessmentSnapshot:
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
        ):
            raise ValueError("limit must be a positive integer")

        with self._connection() as connection, connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            connection.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (f"{self._statement_timeout_ms}ms",),
            )
            limit_sql = " LIMIT %s" if limit is not None else ""
            params: tuple[object, ...] = () if limit is None else (limit,)
            company_rows = connection.execute(
                """SELECT id, business_sector, company_scale, country
                   FROM gold.company
                   ORDER BY id"""
                + limit_sql,
                params,
            ).fetchall()
            companies = tuple(
                CompanyAttributes(
                    company_id=cast(UUID, row[0]),
                    business_sector=None if row[1] is None else tuple(row[1]),
                    company_scale=row[2],
                    country=row[3],
                )
                for row in company_rows
            )
            ids = tuple(company.company_id for company in companies)
            fact_rows = connection.execute(
                """SELECT e.company_id, e.source, e.source_stable_id,
                          e.observation_id, o.snapshot_id, o.raw_token,
                          o.resolution_token, o.context_version, o.policy_version,
                          e.occurred_at, s.source_fields::text
                   FROM gold.current_source_evidence AS e
                   JOIN silver.source_lifecycle_observation AS o
                     ON o.id = e.observation_id
                    AND o.company_id = e.company_id
                    AND o.source = e.source
                    AND o.stable_id = e.source_stable_id
                   JOIN silver.source_context_snapshot AS s
                     ON s.id = o.snapshot_id
                    AND s.source = o.source
                    AND s.stable_id = o.stable_id
                    AND s.parser_version = o.context_version
                   WHERE e.company_id = ANY(%s::uuid[])
                   ORDER BY e.company_id, e.observation_id""",
                (list(ids),),
            ).fetchall()
        facts = tuple(
            SourceFact(
                company_id=cast(UUID, row[0]),
                source=row[1],
                stable_id=row[2],
                observation_id=cast(UUID, row[3]),
                snapshot_id=cast(UUID, row[4]),
                raw_token=row[5],
                resolution_token=row[6],
                context_version=row[7],
                policy_version=row[8],
                occurred_at=row[9],
                source_fields=row[10],
            )
            for row in fact_rows
        )
        return AssessmentSnapshot(
            companies=companies,
            facts=facts,
            scope="all_companies"
            if limit is None
            else f"first_{limit}_companies_by_uuid",
        )

    def candidate_ids(
        self,
        snapshot: AssessmentSnapshot,
        companies: tuple[CompanyAttributes, ...],
        criteria: CompiledCriteria,
        window: SignalWindow,
    ) -> tuple[UUID, ...]:
        """Run the canonical candidate predicate against frozen captured values."""
        company_payload = [
            {
                "id": str(company.company_id),
                "business_sector": company.business_sector,
                "company_scale": company.company_scale,
                "country": company.country,
            }
            for company in companies
        ]
        fact_payload = [
            {
                "company_id": str(fact.company_id),
                "occurred_at": (
                    None if fact.occurred_at is None else fact.occurred_at.isoformat()
                ),
            }
            for fact in snapshot.facts
        ]
        with self._connection() as connection, connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            connection.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (f"{self._statement_timeout_ms}ms",),
            )
            rows = connection.execute(
                _COUNTERFACTUAL_CANDIDATES_SQL,
                (
                    Jsonb(company_payload),
                    Jsonb(fact_payload),
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
        return tuple(cast(UUID, row[0]) for row in rows)


_COUNTERFACTUAL_CANDIDATES_SQL = """
WITH companies AS (
    SELECT id, business_sector, company_scale, country
    FROM jsonb_to_recordset(%s::jsonb) AS c(
        id uuid, business_sector text[], company_scale text, country text)
), facts AS (
    SELECT company_id, occurred_at
    FROM jsonb_to_recordset(%s::jsonb) AS f(company_id uuid, occurred_at timestamptz)
), target AS (
    SELECT ARRAY(SELECT lower(btrim(v)) FROM unnest(%s::text[]) AS t(v)) AS industries,
           %s::text[] AS company_sizes,
           ARRAY(SELECT lower(btrim(v)) FROM unnest(%s::text[]) AS t(v)) AS countries,
           %s::uuid[] AS excluded_company_ids,
           ARRAY(SELECT lower(btrim(v)) FROM unnest(%s::text[]) AS t(v)) AS excluded_industries,
           ARRAY(SELECT lower(btrim(v)) FROM unnest(%s::text[]) AS t(v)) AS excluded_countries
)
SELECT c.id
FROM companies AS c
CROSS JOIN target AS t
JOIN facts AS evidence ON evidence.company_id = c.id
 AND evidence.occurred_at IS NOT NULL
 AND evidence.occurred_at >= %s::timestamptz
 AND evidence.occurred_at <= %s::timestamptz
WHERE EXISTS (
    SELECT 1 FROM unnest(c.business_sector) AS sector(value)
    WHERE sector.value IS NOT NULL AND btrim(sector.value) <> ''
      AND lower(btrim(sector.value)) <> 'unspecified'
      AND lower(btrim(sector.value)) = ANY(t.industries)
)
  AND c.company_scale = ANY(t.company_sizes)
  AND c.country IS NOT NULL AND btrim(c.country) <> ''
  AND lower(btrim(c.country)) = ANY(t.countries)
  AND NOT (c.id = ANY(t.excluded_company_ids))
  AND NOT EXISTS (
      SELECT 1 FROM unnest(c.business_sector) AS sector(value)
      WHERE sector.value IS NOT NULL AND btrim(sector.value) <> ''
        AND lower(btrim(sector.value)) <> 'unspecified'
        AND lower(btrim(sector.value)) = ANY(t.excluded_industries)
  )
  AND NOT (lower(btrim(c.country)) = ANY(t.excluded_countries))
GROUP BY c.id
ORDER BY c.id ASC
"""

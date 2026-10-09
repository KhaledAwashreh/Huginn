"""Read-only collected choices; architecture.md sections 4.3 and 9."""

from uuid import UUID

from huginn.management.application.protocols.configuration_options_query import (
    ConfigurationOptionsQuery,
)
from huginn.management.application.read_models.company_option import CompanyOption
from huginn.management.application.read_models.configuration_option import (
    ConfigurationOption,
)
from huginn.management.application.read_models.configuration_options import (
    ConfigurationOptions,
)
from huginn.management.domain.value_objects.common import Page
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.row_models.company_option import CompanyOptionRow
from huginn.management.persistence.row_models.configuration_option import (
    ConfigurationOptionRow,
)


class PostgresConfigurationOptionsQuery(ConfigurationOptionsQuery):
    def __init__(self, connection: DatabaseSession) -> None:
        self._connection = connection

    def _options(self, sql: str) -> tuple[ConfigurationOption, ...]:
        rows = self._connection.execute(sql).fetchall()
        result = []
        for value, count in rows:
            row = ConfigurationOptionRow(value=value, company_count=count)
            result.append(ConfigurationOption(row.value, row.company_count))
        return tuple(result)

    def options(self) -> ConfigurationOptions:
        industries = self._options(
            """SELECT sector, count(DISTINCT id) FROM gold.company CROSS JOIN LATERAL unnest(business_sector) AS sector WHERE btrim(sector) <> '' AND lower(btrim(sector)) <> 'unspecified' GROUP BY sector ORDER BY lower(sector), sector"""
        )
        countries = self._options(
            """SELECT country, count(*) FROM gold.company WHERE country IS NOT NULL AND btrim(country) <> '' GROUP BY country ORDER BY lower(country), country"""
        )
        sizes = self._options(
            """SELECT company_scale, count(*) FROM gold.company WHERE company_scale IN ('0-10','11-100','101-1000','1001+') GROUP BY company_scale ORDER BY CASE company_scale WHEN '0-10' THEN 0 WHEN '11-100' THEN 1 WHEN '101-1000' THEN 2 ELSE 3 END"""
        )
        return ConfigurationOptions(industries, countries, sizes)

    @staticmethod
    def _company(row: tuple) -> CompanyOption:
        value = CompanyOptionRow(id=row[0], name=row[1], domain=row[2])
        return CompanyOption(value.id, value.name, value.domain)

    def companies(self, search: str, offset: int, limit: int) -> Page[CompanyOption]:
        rows = self._connection.execute(
            """SELECT id,name,domain FROM gold.company WHERE strpos(lower(name),lower(%s)) > 0 OR strpos(lower(coalesce(domain,'')),lower(%s)) > 0 ORDER BY lower(name), id LIMIT %s OFFSET %s""",
            (search, search, limit + 1, offset),
        ).fetchall()
        return Page(
            tuple(self._company(row) for row in rows[:limit]),
            offset,
            limit,
            len(rows) > limit,
        )

    def company(self, company_id: UUID) -> CompanyOption | None:
        row = self._connection.execute(
            "SELECT id,name,domain FROM gold.company WHERE id=%s", (company_id,)
        ).fetchone()
        return None if row is None else self._company(row)

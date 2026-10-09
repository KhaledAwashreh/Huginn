"""Reusable EU staging and downstream materialization stage wiring."""

from __future__ import annotations

from huginn.config import Config
from huginn.elt.gold.company import CompanyWriter
from huginn.elt.gold.company_signal import CompanySignalWriter
from huginn.elt.gold.repositories.company_repository import PostgresCompanyRepository
from huginn.elt.gold.repositories.company_signal_repository import (
    PostgresCompanySignalRepository,
)
from huginn.elt.silver.eu_startups_staging import EuStartupsStagingLoader
from huginn.elt.silver.manual_review import ManualReviewQueuer
from huginn.elt.silver.repositories.eu_startups_staging_repository import (
    PostgresEuStartupsStagingRepository,
)
from huginn.elt.silver.repositories.manual_review_repository import (
    PostgresManualReviewRepository,
)
from huginn.elt.silver.repositories.signal_resolution_repository import (
    PostgresSignalResolutionRepository,
)
from huginn.elt.silver.signal_resolution import SignalResolver
from huginn.elt.stage_runner import Stage


def build_eu_startups_materialization_stages(
    config: Config,
    *,
    resolution_dependencies: tuple[str, ...] = ("silver.eu_startups_staging",),
    include_manual_review: bool = True,
    resolve_eu_startups_only: bool = False,
) -> list[Stage]:
    """Build EU staging and shared Silver/Gold materialization stages.

    Full-pipeline callers retain cross-source resolution by default. A caller
    that refreshes only EU staging can select the EU-only resolver so existing
    HN and YC resolved rows are not read or rewritten.
    """
    eu_startups_staging_loader = EuStartupsStagingLoader(
        PostgresEuStartupsStagingRepository(config.database_url)
    )
    signal_resolver = SignalResolver(
        PostgresSignalResolutionRepository(config.database_url)
    )
    resolve = (
        signal_resolver.resolve_eu_startups
        if resolve_eu_startups_only
        else signal_resolver.resolve_all
    )
    company_writer = CompanyWriter(PostgresCompanyRepository(config.database_url))
    company_signal_writer = CompanySignalWriter(
        PostgresCompanySignalRepository(config.database_url)
    )

    stages = [
        Stage(
            name="silver.eu_startups_staging",
            run=eu_startups_staging_loader.load,
        ),
        Stage(
            name="silver.signal_resolution",
            run=resolve,
            depends_on=resolution_dependencies,
        ),
        Stage(
            name="gold.company",
            run=company_writer.write_all,
            run_managed=company_writer.write_all,
            depends_on=("silver.signal_resolution",),
        ),
        Stage(
            name="gold.company_signal",
            run=company_signal_writer.write_all,
            depends_on=("silver.signal_resolution", "gold.company"),
        ),
    ]
    if include_manual_review:
        manual_review_queuer = ManualReviewQueuer(
            PostgresManualReviewRepository(config.database_url)
        )
        stages.insert(
            2,
            Stage(
                name="silver.manual_review",
                run=manual_review_queuer.queue_unmatched,
                depends_on=("silver.signal_resolution",),
            ),
        )
    return stages

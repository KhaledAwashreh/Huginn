from __future__ import annotations

from huginn.config import Config
from huginn.elt.__main__ import build_stages


def test_build_stages_wires_eu_startups_from_ingestion_through_resolution():
    stages = build_stages(
        Config(
            database_url="postgresql://example.invalid/huginn",
            yc_algolia_api_key="test-key",
        )
    )
    by_name = {stage.name: stage for stage in stages}

    assert "ingestion.eu_startups" in by_name
    discovery_runner = by_name["ingestion.eu_startups"].run.__self__
    assert discovery_runner._allow_initial_backfill is False
    assert by_name["silver.eu_startups_staging"].depends_on == (
        "ingestion.eu_startups",
    )
    assert by_name["silver.signal_resolution"].depends_on == (
        "silver.hn_staging",
        "silver.yc_staging",
        "silver.eu_startups_staging",
    )
    assert by_name["gold.company"].depends_on == ("silver.signal_resolution",)
    assert by_name["gold.company_signal"].depends_on == (
        "silver.signal_resolution",
        "gold.company",
    )

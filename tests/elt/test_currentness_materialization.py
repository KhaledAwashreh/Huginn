import pytest

from huginn.config import Config
from huginn.elt import materialization
from huginn.elt.__main__ import build_stages
from huginn.elt.materialization import build_eu_startups_materialization_stages
from huginn.pipeline_control.domain.value_objects.stage_plan import SUPPORTED_STAGE_PLAN


def test_full_pipeline_reconciles_each_source_after_gold_materialization():
    stages = build_stages(
        Config(
            database_url="postgresql://example.invalid/test", yc_algolia_api_key="test"
        )
    )
    by_name = {stage.name: stage for stage in stages}
    for source in ("hn", "yc", "eu_startups"):
        assert by_name[f"silver.source_currentness.{source}"].depends_on == (
            "gold.company_signal",
        )
    assert tuple(by_name) == tuple(stage.name for stage in SUPPORTED_STAGE_PLAN.stages)


def test_eu_only_materialization_does_not_reconcile_unmaterialized_sources():
    stages = build_eu_startups_materialization_stages(
        Config(
            database_url="postgresql://example.invalid/test", yc_algolia_api_key="test"
        ),
        resolve_eu_startups_only=True,
    )
    assert [stage.name for stage in stages if "currentness" in stage.name] == [
        "silver.source_currentness.eu_startups"
    ]


@pytest.mark.parametrize(
    "report",
    [
        {"status": "partial", "error_type": "stale", "completed_count": 0},
        {
            "status": "partial",
            "error_type": "ValueError",
            "completed_count": 1,
            "reconcile_counts": {"created": 1, "unchanged": 0, "stale": 0},
        },
    ],
)
def test_currentness_stage_fails_on_stale_or_partial_reconciliation(
    monkeypatch: pytest.MonkeyPatch, report: dict[str, object]
) -> None:
    monkeypatch.setattr(materialization, "run_reconcile", lambda *_args: report)
    stage = next(
        stage
        for stage in build_eu_startups_materialization_stages(
            Config(
                database_url="postgresql://example.invalid/test",
                yc_algolia_api_key="test",
            ),
            resolve_eu_startups_only=True,
        )
        if stage.name == "silver.source_currentness.eu_startups"
    )

    with pytest.raises(RuntimeError, match="reconciliation incomplete"):
        stage.run()


def test_currentness_stage_preserves_reconciliation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args):
        raise OSError("database unavailable")

    monkeypatch.setattr(materialization, "run_reconcile", fail)
    stage = next(
        stage
        for stage in build_eu_startups_materialization_stages(
            Config(
                database_url="postgresql://example.invalid/test",
                yc_algolia_api_key="test",
            ),
            resolve_eu_startups_only=True,
        )
        if stage.name == "silver.source_currentness.eu_startups"
    )

    with pytest.raises(OSError, match="database unavailable"):
        stage.run()

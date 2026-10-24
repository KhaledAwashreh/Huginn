"""Assessment reports preserve frozen inputs and disclose uncertainty."""

from datetime import UTC, datetime
from uuid import UUID

from huginn.elt.gold.models.assessment_snapshot import AssessmentSnapshot
from huginn.elt.gold.models.company_attributes import CompanyAttributes
from huginn.elt.gold.models.source_fact import SourceFact
from huginn.elt.gold.services.attribute_assessment import run_assessment
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow

NOW = datetime(2026, 10, 1, tzinfo=UTC)
COMPANY = UUID(int=1)
CRITERIA = CompiledCriteria(("B2B",), ("0-10",), ("Germany",), (), (), ())


class Repository:
    def __init__(self):
        self.reads = 0
        self.snapshot = AssessmentSnapshot(
            (CompanyAttributes(COMPANY, None, None, "Germany"),),
            (
                SourceFact(
                    COMPANY,
                    "yc",
                    "public-id",
                    UUID(int=2),
                    UUID(int=3),
                    "raw-token",
                    "resolution-token",
                    "yc-context-v1",
                    "source-lifecycle-v1",
                    NOW,
                    '{"team_size":0,"industries":["B2B"]}',
                ),
            ),
            "all_companies",
        )

    def read_snapshot(self, limit=None):
        self.reads += 1
        return self.snapshot

    def candidate_ids(self, snapshot, companies, criteria, window):
        assert snapshot is self.snapshot
        return tuple(
            c.company_id
            for c in companies
            if c.business_sector == ("B2B",) and c.company_scale == "0-10"
        )


def test_report_uses_one_snapshot_and_keeps_sensitive_receipts_separate():
    repository = Repository()
    result = run_assessment(
        repository, {"synthetic": CRITERIA}, {"fixed": SignalWindow(NOW, NOW)}
    )
    assert repository.reads == 1
    report = result.summary
    assert report["company_count"] == 1
    assert report["field_outcomes"]["business_sector"]["proposed"] == 1
    impact = report["comparisons"][0]
    assert (
        impact["before"],
        impact["after"],
        impact["newly_eligible"],
        impact["lost"],
    ) == (0, 1, 1, 0)
    assert str(COMPANY) not in str(report)
    assert "raw-token" not in str(report)
    assert "public-id" not in str(report)
    assert result.receipts[0]["company_id"] == str(COMPANY)
    assert result.receipts[0]["supporting_facts"][0]["raw_token"] == "raw-token"


def test_assessment_is_deterministic_and_does_not_mutate_inputs():
    repository = Repository()
    original = repository.snapshot
    first = run_assessment(
        repository, {"synthetic": CRITERIA}, {"fixed": SignalWindow(NOW, NOW)}
    )
    second = run_assessment(
        repository, {"synthetic": CRITERIA}, {"fixed": SignalWindow(NOW, NOW)}
    )
    assert first == second
    assert repository.snapshot == original
    assert repository.snapshot.companies[0].company_scale is None


def test_no_evidence_is_disclosed_without_fabricating_attributes():
    repository = Repository()
    repository.snapshot = AssessmentSnapshot(
        repository.snapshot.companies, (), "limited_sample"
    )
    result = run_assessment(
        repository, {"synthetic": CRITERIA}, {"fixed": SignalWindow(NOW, NOW)}, limit=1
    )
    assert result.summary["selection"] == {"limit": 1, "scope": "limited_sample"}
    assert result.summary["companies_without_guarded_evidence"] == 1
    assert result.summary["companies_with_guarded_evidence"] == 0
    assert result.summary["field_outcomes"]["company_scale"]["unsupported"] == 1
    assert result.summary["comparisons"][0]["after"] == 0


def test_alias_counterfactual_normalizes_positive_and_negative_countries_together():
    from dataclasses import replace

    repository = Repository()
    repository.snapshot = replace(
        repository.snapshot,
        companies=(replace(repository.snapshot.companies[0], country=" USA "),),
    )
    calls = []

    def candidates(snapshot, companies, criteria, window):
        calls.append((companies, criteria))
        return ()

    repository.candidate_ids = candidates
    target = replace(
        CRITERIA, countries=("USA",), excluded_countries=("United States",)
    )
    run_assessment(repository, {"synthetic": target}, {"fixed": SignalWindow(NOW, NOW)})
    assert calls[0][1] == target
    assert calls[1][1] == target
    alias_companies, alias_target = calls[2]
    assert alias_companies[0].country == "united states"
    assert (
        alias_target.countries == alias_target.excluded_countries == ("united states",)
    )


def test_fingerprint_covers_company_values_and_source_versions():
    from dataclasses import replace

    repository = Repository()
    baseline = run_assessment(
        repository, {"synthetic": CRITERIA}, {"fixed": SignalWindow(NOW, NOW)}
    ).summary["input_fingerprint"]
    repository.snapshot = replace(
        repository.snapshot,
        facts=(replace(repository.snapshot.facts[0], raw_token="new-token"),),
    )
    changed = run_assessment(
        repository, {"synthetic": CRITERIA}, {"fixed": SignalWindow(NOW, NOW)}
    ).summary["input_fingerprint"]
    assert changed != baseline
    repository.snapshot = replace(
        repository.snapshot,
        companies=(replace(repository.snapshot.companies[0], country="France"),),
    )
    assert (
        run_assessment(
            repository, {"synthetic": CRITERIA}, {"fixed": SignalWindow(NOW, NOW)}
        ).summary["input_fingerprint"]
        != changed
    )


def test_catalog_identity_is_reported_only_when_catalog_was_supplied():
    from huginn.elt.gold.models.catalog_region import CatalogRegion
    from huginn.elt.gold.models.yc_geography_catalog import YcGeographyCatalog

    repository = Repository()
    base = run_assessment(
        repository, {"synthetic": CRITERIA}, {"fixed": SignalWindow(NOW, NOW)}
    )
    assert "yc_geography_catalog" not in base.summary
    catalog = YcGeographyCatalog.create(
        (CatalogRegion("Germany", 1), CatalogRegion("Georgia", 1)),
        country_labels=("Germany",),
        unknown_labels=(),
        ambiguous_labels=("Georgia",),
        fetched_at=NOW,
        reference_version="test-reference",
    )
    result = run_assessment(
        repository,
        {"synthetic": CRITERIA},
        {"fixed": SignalWindow(NOW, NOW)},
        yc_geography_catalog=catalog,
    )
    assert result.summary["yc_geography_catalog"] == {
        "fingerprint": catalog.fingerprint,
        "schema_version": catalog.schema_version,
        "classifier_version": catalog.classifier_version,
        "reference_version": catalog.reference_version,
        "fetched_at": catalog.fetched_at.isoformat(),
    }
    assert result.receipts[0]["yc_geography_catalog_fingerprint"] == catalog.fingerprint
    assert (
        result.receipts[0]["yc_geography_catalog_reference_version"]
        == catalog.reference_version
    )

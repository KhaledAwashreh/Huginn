from collections.abc import Mapping
from uuid import UUID

from huginn.matchmaking.domain.constants.targeting import (
    COMPANY_SIZE_BANDS,
    UNKNOWN_INDUSTRY,
)
from huginn.matchmaking.domain.errors.criteria import CriteriaIssue, CriteriaIssueReason
from huginn.matchmaking.domain.types.json_value import RawJsonValue
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria


def compile_icp(
    *,
    industries: RawJsonValue,
    company_sizes: RawJsonValue,
    geographies: RawJsonValue,
    exclusions: RawJsonValue,
) -> CompiledCriteria | CriteriaIssue:
    parsed_industries = _objects(industries, {"name"})
    parsed_sizes = _objects(company_sizes, {"band"})
    parsed_geographies = _objects(geographies, {"kind", "value"})
    parsed_exclusions = _array(exclusions)
    if any(
        value is None
        for value in (
            parsed_industries,
            parsed_sizes,
            parsed_geographies,
            parsed_exclusions,
        )
    ):
        return CriteriaIssue(CriteriaIssueReason.INVALID_ICP)

    industry_names: list[str] = []
    for item in parsed_industries:
        name = _text(item["name"])
        if name is None or _norm(name) == _norm(UNKNOWN_INDUSTRY):
            return CriteriaIssue(CriteriaIssueReason.INVALID_ICP)
        industry_names.append(name)

    size_names: list[str] = []
    for item in parsed_sizes:
        band = item["band"]
        if not isinstance(band, str) or band not in COMPANY_SIZE_BANDS:
            return CriteriaIssue(CriteriaIssueReason.INVALID_ICP)
        size_names.append(band)

    countries: list[str] = []
    regions = False
    for item in parsed_geographies:
        kind, value = item["kind"], _text(item["value"])
        if kind not in ("country", "region") or value is None:
            return CriteriaIssue(CriteriaIssueReason.INVALID_ICP)
        if kind == "region":
            regions = True
        else:
            countries.append(value)

    company_ids: list[UUID] = []
    excluded_industries: list[str] = []
    excluded_countries: list[str] = []
    for item in parsed_exclusions:
        if not isinstance(item, Mapping) or not isinstance(item.get("kind"), str):
            return CriteriaIssue(CriteriaIssueReason.INVALID_ICP)
        kind = item["kind"]
        if kind == "company" and set(item) == {"kind", "company_id"}:
            raw_id = item["company_id"]
            if not isinstance(raw_id, str):
                return CriteriaIssue(CriteriaIssueReason.INVALID_ICP)
            try:
                company_ids.append(UUID(raw_id))
            except ValueError:
                return CriteriaIssue(CriteriaIssueReason.INVALID_ICP)
        elif kind == "industry" and set(item) == {"kind", "name"}:
            name = _text(item["name"])
            if name is None:
                return CriteriaIssue(CriteriaIssueReason.INVALID_ICP)
            excluded_industries.append(name)
        elif kind == "geography" and set(item) == {"kind", "geography"}:
            geo = item["geography"]
            if not isinstance(geo, Mapping) or set(geo) != {"kind", "value"}:
                return CriteriaIssue(CriteriaIssueReason.INVALID_ICP)
            value = _text(geo["value"])
            if geo["kind"] not in ("country", "region") or value is None:
                return CriteriaIssue(CriteriaIssueReason.INVALID_ICP)
            if geo["kind"] == "region":
                regions = True
            else:
                excluded_countries.append(value)
        else:
            return CriteriaIssue(CriteriaIssueReason.INVALID_ICP)

    if not industry_names or not size_names or not parsed_geographies:
        return CriteriaIssue(CriteriaIssueReason.INCOMPLETE_ICP)
    if regions:
        return CriteriaIssue(CriteriaIssueReason.UNSUPPORTED_REGION)
    return CompiledCriteria(
        industries=_unique(industry_names),
        company_sizes=_unique(size_names),
        countries=_unique(countries),
        excluded_company_ids=tuple(
            sorted(set(company_ids), key=lambda value: value.int)
        ),
        excluded_industries=_unique(excluded_industries),
        excluded_countries=_unique(excluded_countries),
    )


def _array(value: RawJsonValue) -> tuple[RawJsonValue, ...] | None:
    return value if isinstance(value, tuple) else None


def _objects(
    value: RawJsonValue, keys: set[str]
) -> tuple[Mapping[str, RawJsonValue], ...] | None:
    items = _array(value)
    if items is None:
        return None
    result = []
    for item in items:
        if not isinstance(item, Mapping) or set(item) != keys:
            return None
        result.append(item)
    return tuple(result)


def _text(value: RawJsonValue) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip(" ")
    return value if value else None


def _norm(value: str) -> str:
    return value.strip(" ").lower()


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({value.strip(" ") for value in values}))

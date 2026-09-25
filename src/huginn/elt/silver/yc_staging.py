"""YC staging loader: bronze.api_ingest (source="yc") -> silver.yc_listings.
See architecture document section 4.2, ADR-0001, docs/entities.md's
YcListingStaging. Jira KAN-34.

signal_type follows isHiring: "hiring" when true, "program_milestone"
otherwise (the listing itself, whatever its current hiring state, is
still a trackable signal; the payload carries no funding data, so
"funding" is never produced here). Confirmed live: exactly two `stage`
values exist ("Early", "Growth"), passed through unmapped. See this
plan's Task 4 "Grounding" note.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from huginn.elt.silver.models import YcListingStaging
from huginn.elt.silver.ports import YcStagingRepositoryPort

logger = logging.getLogger(__name__)

_YC_COMPANY_URL = "https://www.ycombinator.com/companies/{slug}"

# YC's own lifecycle vocabulary, confirmed on all 6,252 live rows: Active,
# Inactive, Acquired, Public. These two mean the company is not a lead.
_EXCLUDED_STATUSES = frozenset({"Acquired", "Inactive"})


def _as_str_tuple(value: object) -> tuple[str, ...] | None:
    """Return a source list of strings as a tuple, or None when absent.

    None and () have to stay distinguishable, because Gold treats a NULL as
    "this source does not report the field" and skips the column, whereas an
    empty array would be written as a real value.
    """
    if value is None:
        return None
    return tuple(value)


def parse_yc_listing(payload: dict) -> YcListingStaging | None:
    """Parse one YC Algolia hit, or return None if the company is one this
    tool has no use for: acquired, or inactive.

    An acquired company is not a prospect, it is a product of one, and an
    inactive one is no longer operating under its own name. Both are still
    landed in bronze, exactly as fetched, and both stay there; this is the
    bronze-to-silver step declining to promote them (architecture document
    section 4.1 keeps bronze as the as-fetched record).

    `Public` is deliberately kept. A listed company is also not a prospect,
    but the rule being implemented is "no longer operating independently",
    not "not Active", and the narrower rule is the one that stays true as YC's
    vocabulary grows. A missing status is kept too: absent means the source
    did not say, which is not the same claim as acquired.

    Never returns None for any other reason: `id`, `name`, and `slug` are
    present on 100% of the live directory (confirmed, this plan's Task 4),
    unlike HN's freeform comments.
    """
    if payload.get("status") in _EXCLUDED_STATUSES:
        return None

    description = payload.get("long_description") or payload["one_liner"]

    return YcListingStaging(
        stable_id=str(payload["id"]),
        company_name_raw=payload["name"],
        website=payload.get("website"),
        signal_type="hiring" if payload.get("isHiring") else "program_milestone",
        stage=payload.get("stage"),
        company_status=payload.get("status"),
        team_size=payload.get("team_size"),
        industries=_as_str_tuple(payload.get("industries")),
        all_locations=payload.get("all_locations"),
        former_names=_as_str_tuple(payload.get("former_names")),
        batch=payload.get("batch"),
        description=description,
        occurred_on=datetime.fromtimestamp(payload["launched_at"], tz=UTC),
        url=_YC_COMPANY_URL.format(slug=payload["slug"]),
    )


class YcStagingLoader:
    """Reads bronze.api_ingest (source="yc") and upserts silver.yc_listings
    via its injected port. See docs/entities.md's YcListingStaging and
    ADR-0001. Jira KAN-34. See huginn.elt.silver.ports for the port
    contract; this class holds no persistence detail of its own.

    Reads every bronze row for the source each run rather than tracking
    its own watermark: silver.yc_listings' UNIQUE(stable_id) upsert
    already makes re-processing idempotent, mirroring Bronze's own
    hash-based idempotency (architecture document section 4.1). The
    upsert still writes every row on every run; it is the resulting
    database state, not the work done, that is unchanged.
    """

    def __init__(self, repository: YcStagingRepositoryPort) -> None:
        self._repository = repository

    def load(self) -> int:
        """Parse and upsert every current YC bronze row, returning the
        count of rows upserted.

        That is fewer than the bronze row count whenever a company is
        acquired or inactive: `parse_yc_listing` returns None for those and
        they are skipped, so silver holds only companies this tool can act
        on. For every row that is kept the write still executes even when
        nothing changed; it is the resulting database state, not the work
        done, that is unchanged.

        The filter gates promotion, it does not retract it. A company staged
        while Active and later reported Acquired keeps its existing row: the
        next load reads the same `stable_id`, skips it, and writes nothing,
        so the stale `company_status` stays until something removes the row
        (a full rebuild, or a delete on status transition that this design
        deliberately does not do). Bronze is unaffected either way, since
        it is the as-fetched record and is never rewritten by this step.
        """
        # See huginn.elt.silver.ports's module docstring for why this whole
        # method shares one `with self._repository:` scope.
        with self._repository:
            payloads = self._repository.read("yc")
            written = 0
            excluded = 0
            for payload in payloads:
                staging_row = parse_yc_listing(payload)
                if staging_row is None:
                    excluded += 1
                    continue
                self._repository.upsert(staging_row)
                written += 1

        logger.info(
            "silver.yc_listings load: %d written, %d skipped as acquired/inactive "
            "(of %d bronze rows)",
            written,
            excluded,
            len(payloads),
        )
        return written

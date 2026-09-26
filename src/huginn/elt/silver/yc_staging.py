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

# The exception types a malformed Algolia hit can produce. Dict indexing and
# list coercion give KeyError and TypeError. `datetime.fromtimestamp` gives
# TypeError for a non-number, then three distinct out-of-range bands as the
# magnitude grows: ValueError first, for a timestamp the calendar cannot
# represent (1e12 is year 33658), then OverflowError past the platform's
# `time_t`, then OSError with errno 75 where the C library refuses the value
# outright. The last two are not ValueError subclasses and the order is not
# obvious, so all three are named and all three are tested. Per
# BEST_PRACTICES.md:197-200, catch the narrowest type actually expected
# rather than bare `Exception`, so a bug of an unexpected class (an
# AttributeError from a non-mapping payload, say) still propagates. See
# `YcStagingLoader.load` for what this deliberately does not cover.
_UNPARSEABLE_PAYLOAD_ERRORS = (
    KeyError,
    TypeError,
    ValueError,
    OverflowError,
    OSError,
)


# The complete set of reasons a hit is not promoted, as named constants so
# `parse_yc_listing` and `YcStagingLoader.load` cannot drift apart. Add a
# reason here and `load` will count it as unclassified and warn, rather than
# quietly filing it under a business rule it is not.
_SKIP_NOT_A_PROSPECT = "not a prospect (acquired/inactive)"
_SKIP_ABSENT_LAUNCH_DATE = "absent or null launched_at"


def _listing_field(payload: object, field: str) -> object:
    """Read one payload field for a log line, or None when not readable.

    The `isinstance` guard rather than a bare `payload.get` because this runs
    on the rejection path, where the payload may be the very thing that
    failed. Nothing further is needed: a bronze payload is JSONB and therefore
    always a real dict, and a dict's `.get` cannot raise, so the handler
    cannot fail while building its own log line. Wrapping this in a broad
    `except` to defend against an unreachable case would break
    BEST_PRACTICES.md:197-200 for no gain.
    """
    return payload.get(field) if isinstance(payload, dict) else None


def _as_str_tuple(value: object) -> tuple[str, ...] | None:
    """Return a source list of strings as a tuple, or None when absent.

    None and () have to stay distinguishable, because Gold treats a NULL as
    "this source does not report the field" and skips the column, whereas an
    empty array would be written as a real value.
    """
    if value is None:
        return None
    return tuple(value)


def _skip_reason(payload: dict) -> str | None:
    """Why this hit cannot be promoted, or None when it can.

    The only place the skip conditions are written. `parse_yc_listing` and
    `YcStagingLoader.load` both read this rather than each testing the
    payload, so a new reason cannot be added to one and missed by the other.
    The two reasons are deliberately distinct in kind: an acquired or
    inactive company is a business-rule exclusion, while a missing launch
    date is a source-side data problem, and reporting them as one number
    would hide the second behind the first.
    """
    if payload.get("status") in _EXCLUDED_STATUSES:
        return _SKIP_NOT_A_PROSPECT
    if payload.get("launched_at") is None:
        return _SKIP_ABSENT_LAUNCH_DATE
    return None


def parse_yc_listing(payload: dict) -> YcListingStaging | None:
    """Parse one YC Algolia hit, or return None when the company is not one
    this tool can act on. Architecture document section 4.1: bronze keeps
    every hit as fetched, so declining to promote is a silver decision and
    loses nothing.

    Two ways to get None, both named by `_skip_reason`: acquired or
    inactive (not operating independently under its own name), and absent or
    null `launched_at` (`occurred_on` is the signal's own date and no layer
    invents a substitute). A payload too malformed to parse raises instead,
    and `YcStagingLoader.load` is what turns that into a counted, logged
    skip. This function does not log: `load` checks `_skip_reason` before
    calling it, so a warning emitted here would never fire on the pipeline's
    own path. Reporting belongs at the stage boundary, per ADR-0005.

    `Public` and a missing status are both deliberately kept. The rule is
    "no longer operating independently", not "not Active", and that stays
    true as YC's vocabulary grows. Absent means the source did not say, which
    is not the same claim as acquired.

    A missing optional field is not grounds for declining a row, only for a
    thinner one, and the two are different policies on purpose. `id` and
    `slug` are indexed directly, because without them there is no stable key
    and no company URL; `name` because a company row with no name is not a
    lead. Everything else is fetched with a default, so an unreported field
    reads as NULL rather than as an empty value, following the same
    NULL-versus-empty distinction `_as_str_tuple` documents.
    """
    if _skip_reason(payload) is not None:
        return None

    # `long_description` first, `one_liner` as the shorter fallback. The `or`
    # is load-bearing on both sides: 386 live rows carry an empty
    # `long_description`, and 344 of those have a populated `one_liner`, so
    # testing for None instead would drop their text. This yields NULL when
    # neither key is there, "" when both are empty, and the fallback
    # otherwise, which keeps "not reported" distinct from "reported as
    # nothing" the way `_as_str_tuple` does for the list columns.
    description = payload.get("long_description") or payload.get("one_liner")

    # Indexed, not fetched with a default: `_skip_reason` has already
    # established that this key is present and not None.
    launched_at = payload["launched_at"]

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
        occurred_on=datetime.fromtimestamp(launched_at, tz=UTC),
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
        """Parse and upsert every current YC bronze row, returning the count
        of rows upserted. Fewer than the bronze row count, because hits that
        are not prospects, whose `launched_at` is absent or null, that are
        skipped for a reason this summary does not yet name, or that cannot be
        parsed are all declined; each has its own count, and an unnamed reason
        is warned rather than folded into a bucket.

        An unparseable hit is caught rather than allowed to escape because
        bronze is immutable and re-read whole every run, so an escaping
        error is not one lost run but a permanent outage for the table.
        `huginn.elt.silver.ports` owns why the batch shares one transaction.

        `_UNPARSEABLE_PAYLOAD_ERRORS` cannot by itself tell bad source data
        from a bug here, because KeyError, TypeError and ValueError are what
        both raise. That is the accepted cost of not catching bare
        `Exception`: a defect of one of those classes surfaces as a rising
        rejected count and a per-row record naming the id, not as a traceback.
        A defect of any other class still propagates. An exception from
        `upsert` is deliberately not caught, since a SQL error aborts the
        transaction and swallowing it would hide a real failure without
        recovering the batch. That guard is a parser-shape guard, not a type
        guard: a field that parses but carries the wrong type, a `dict` where
        a string belongs, reaches Postgres and is rejected there, which rolls
        the batch back the same way. No live row does that today; it is
        source-drift exposure, not a current fault.

        A declined row is logged with `logger.warning`, not the
        `logger.exception` ADR-0005 asks for at the point handling a failure.
        A decline is an expected, counted outcome of untrusted input rather
        than a fault, and a traceback per bad row would bury the batch
        summary that is the actual report. Nothing is swallowed: every
        decline is counted, and the run summary names how many of each kind.

        The status filter gates promotion, it does not retract it. A company
        staged while Active and later reported Acquired keeps its row, and
        its stale `company_status` stays until a full rebuild, because this
        design does not delete on status transition.

        `_skip_reason` is status-first, so a hit that is both acquired and
        undated is counted only as not a prospect, and its missing date is
        not separately reported.
        """
        # See huginn.elt.silver.ports's module docstring for why this whole
        # method shares one `with self._repository:` scope.
        with self._repository:
            payloads = self._repository.read("yc")
            written = 0
            not_a_prospect = 0
            no_launch_date = 0
            unclassified = 0
            rejected = 0
            for payload in payloads:
                try:
                    reason = _skip_reason(payload)
                    staging_row = None if reason else parse_yc_listing(payload)
                except _UNPARSEABLE_PAYLOAD_ERRORS as error:
                    rejected += 1
                    logger.warning(
                        "silver.yc_listings: rejected unparseable listing "
                        "id=%r (%s: %s)",
                        _listing_field(payload, "id"),
                        type(error).__name__,
                        error,
                    )
                    continue
                if staging_row is not None:
                    self._repository.upsert(staging_row)
                    written += 1
                    continue
                if reason == _SKIP_NOT_A_PROSPECT:
                    # Count only, no per-row warning: 1,903 of 6,252 live rows
                    # are excluded this way, so naming each one would bury
                    # the summary and the genuinely surprising buckets.
                    not_a_prospect += 1
                elif reason == _SKIP_ABSENT_LAUNCH_DATE:
                    no_launch_date += 1
                    logger.warning(
                        "silver.yc_listings: not promoting listing id=%r "
                        "(name=%r): %s, and occurred_on has no substitute",
                        _listing_field(payload, "id"),
                        _listing_field(payload, "name"),
                        reason,
                    )
                else:
                    # A reason added to `_skip_reason` without a bucket here.
                    # Counted and warned rather than filed under a business
                    # rule it is not, which would drop the row in silence.
                    unclassified += 1
                    logger.warning(
                        "silver.yc_listings: skipped listing id=%r for an "
                        "unclassified reason (%r); it was not promoted and has "
                        "no summary bucket",
                        _listing_field(payload, "id"),
                        reason,
                    )

        logger.info(
            "silver.yc_listings load: %d written, %d skipped as not a prospect, "
            "%d skipped for an absent or null launched_at, %d skipped for an "
            "unclassified reason, %d rejected as unparseable "
            "(of %d bronze rows)",
            written,
            not_a_prospect,
            no_launch_date,
            unclassified,
            rejected,
            len(payloads),
        )
        return written

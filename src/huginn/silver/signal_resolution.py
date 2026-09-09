"""Cross-source entity resolution and silver.resolved_signals writer.
See architecture document section 6, ADR-0001, docs/entities.md's
ResolvedSignal. Jira KAN-35.

Domain-key matching only (architecture document section 6's first
step). The Jaro-Winkler/token-Jaccard fallback is unimplemented debt
(Jira KAN-4, see huginn.silver.resolution.fuzzy_match) and out of this
plan's scope: a row with no matchable domain gets a synthetic
placeholder key (this plan's Task 6) and match_confidence =
"no_existing_match", never a fabricated real-looking key or a NULL
(resolved_company_key is NOT NULL). Task 7 queues every such row for
manual review.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from huginn.silver.ports import ResolvedSignalRecord
from huginn.silver.resolution import MatchConfidence, normalize_domain

if TYPE_CHECKING:
    from huginn.silver.ports import ResolvedSignalWriterPort, SilverStagingReaderPort

logger = logging.getLogger(__name__)


_NON_COMPANY_HOSTS = frozenset(
    {
        "ashbyhq.com",
        "bamboohr.com",
        "curriculo.me",
        "greenhouse.io",
        "lever.co",
        "myworkdayjobs.com",
        "producthunt.com",
        "workday.com",
        "ycombinator.com",
        "youtube.com",
    }
)
"""Hosts that are never a company's own domain: ATS/careers platforms and
generic content platforms. Sourced from this plan's final review, which
found live false merges caused by treating them as company keys: "Uiflow"
and "Y Combinator" both resolved to `ycombinator.com`, "Product Hunt" and
"Storyline" both to `producthunt.com`, and several HN postings to the ATS
host in their posting link rather than the hiring company's own site.
"""


def _is_non_company_host(domain: str) -> bool:
    """True when `domain` is a denylisted host or a subdomain of one
    (`boards.greenhouse.io`, `acme.bamboohr.com`). Suffix matching is on
    label boundaries, so `notgreenhouse.io` is unaffected.
    """
    return any(
        domain == host or domain.endswith(f".{host}") for host in _NON_COMPANY_HOSTS
    )


def unresolved_placeholder_key(source: str, source_stable_id: str) -> str:
    """Synthetic resolved_company_key for a row with no extractable
    domain. Scoped by (source, source_stable_id), not company_name_raw,
    so two different companies sharing a raw name string are never
    merged under one placeholder while both await manual review.
    """
    return f"unresolved:{source}:{source_stable_id}"


def resolve_signal(
    source: str, source_stable_id: str, website: str | None
) -> tuple[str, str]:
    """Decide (resolved_company_key, match_confidence) for one staging
    row. See architecture document section 6: domain is the canonical
    key; no domain match falls through to "no_existing_match" (the
    fuzzy fallback is unimplemented, Jira KAN-4).

    A domain in `_NON_COMPANY_HOSTS` is not a match. `website` is
    freeform on both sources (HN's link extraction, YC's raw directory
    field) and sometimes carries an ATS or platform host instead of the
    company's own site; this plan's final review found those hosts
    auto-matching and merging unrelated companies under one key. A wrong
    confident match is worse than none, so these route to manual review
    like any other unmatchable row.
    """
    if website:
        domain = normalize_domain(website)
        if domain and not _is_non_company_host(domain):
            return domain, MatchConfidence.AUTO_MATCHED
    return (
        unresolved_placeholder_key(source, source_stable_id),
        MatchConfidence.NO_EXISTING_MATCH,
    )


class SignalResolver:
    """Reads every per-source staging table and upserts
    silver.resolved_signals via its injected ports. See
    docs/entities.md's ResolvedSignal. Jira KAN-35. See
    huginn.silver.ports for the port contracts; this class holds no
    persistence detail of its own.
    """

    def __init__(
        self,
        staging_reader: SilverStagingReaderPort,
        resolved_writer: ResolvedSignalWriterPort,
    ) -> None:
        self._staging_reader = staging_reader
        self._resolved_writer = resolved_writer

    def resolve_all(self) -> int:
        """Resolve and upsert every staged signal from every source,
        returning the count of rows upserted (always equals the input
        count; the write executes on every row even when nothing
        changed).
        """
        staged_signals = (
            self._staging_reader.read_hn_postings()
            + self._staging_reader.read_yc_listings()
        )

        written = 0
        for signal in staged_signals:
            resolved_company_key, match_confidence = resolve_signal(
                signal.source, signal.stable_id, signal.website
            )
            self._resolved_writer.upsert(
                ResolvedSignalRecord(
                    source=signal.source,
                    source_stable_id=signal.stable_id,
                    resolved_company_key=resolved_company_key,
                    company_name_raw=signal.company_name_raw,
                    signal_type=signal.signal_type,
                    stage=signal.stage,
                    description=signal.description,
                    occurred_on=signal.occurred_on,
                    url=signal.url,
                    match_confidence=match_confidence,
                )
            )
            written += 1

        logger.info("silver.resolved_signals resolve_all: %d written", written)
        return written

"""Cross-source entity resolution and silver.resolved_signals writer.
See architecture document section 6, ADR-0001, docs/entities.md's
ResolvedSignal. Jira KAN-35.

Domain-key normalization only (architecture document section 6's first
step). The Jaro-Winkler/token-Jaccard fallback is unimplemented debt
(Jira KAN-4, see huginn.elt.silver.resolution.fuzzy_match) and out of this
plan's scope: a row with no derivable domain gets a synthetic
placeholder key (this plan's Task 6) and key_derivation =
"unresolved", never a fabricated real-looking key or a NULL
(resolved_company_key is NOT NULL). Task 7 queues every such row for
manual review.
"""

from __future__ import annotations

import logging

from huginn.elt.silver.models import ResolvedSignalRecord
from huginn.elt.silver.ports import SignalResolutionRepositoryPort
from huginn.elt.silver.resolution import (
    KeyDerivation,
    check_domain_reachable,
    normalize_domain,
)

logger = logging.getLogger(__name__)

# How often resolve_all() logs progress at INFO, in rows processed. See
# adr/0014's Context section: this stage's real network round trips per
# row can add up to 30+ minutes with no database write until the end, so
# a periodic, named progress line is what turns a long run into a visible
# advance instead of an indistinguishable-from-a-hang wait. 100 balances
# that against not flooding the log at real project volume (~6,000+
# rows), yielding on the order of dozens of lines per run rather than
# thousands.
_PROGRESS_LOG_INTERVAL = 100


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
    """Decide (resolved_company_key, key_derivation) for one staging
    row. See architecture document section 6: domain normalization is the
    canonical key source; no derivable domain falls through to
    "unresolved" (the fuzzy fallback is unimplemented, Jira KAN-4).

    A domain in `_NON_COMPANY_HOSTS` doesn't count as derivable. `website`
    is freeform on both sources (HN's link extraction, YC's raw directory
    field) and sometimes carries an ATS or platform host instead of the
    company's own site; this plan's final review found those hosts
    producing a confident-looking key that merged unrelated companies. A
    wrong confident key is worse than none, so these route to manual
    review like any other unresolvable row.

    A domain must also pass `check_domain_reachable` to earn
    `DOMAIN_NORMALIZED` (Jira KAN-62). A transient network failure is
    retried once inside `check_domain_reachable` itself rather than
    distinguished from a confident negative here (see this plan's Global
    Constraint 3).
    """
    if website:
        domain = normalize_domain(website)
        if (
            domain
            and not _is_non_company_host(domain)
            and check_domain_reachable(domain)
        ):
            return domain, KeyDerivation.DOMAIN_NORMALIZED
    return (
        unresolved_placeholder_key(source, source_stable_id),
        KeyDerivation.UNRESOLVED,
    )


class SignalResolver:
    """Reads every per-source staging table and upserts
    silver.resolved_signals via its injected port. See
    docs/entities.md's ResolvedSignal. Jira KAN-35. See
    huginn.elt.silver.ports for the port contract; this class holds no
    persistence detail of its own.
    """

    def __init__(self, repository: SignalResolutionRepositoryPort) -> None:
        self._repository = repository

    def resolve_all(self) -> int:
        """Resolve and upsert every staged signal from every source,
        returning the count of rows upserted (always equals the input
        count; the write executes on every row even when nothing
        changed).

        Reads and writes open two separate connection scopes rather than
        one shared scope, so `resolve_signal()`'s network call (Jira
        KAN-62) never runs while a database connection is held open. See
        ADR-0006 for why this deviates from `huginn.elt.silver.ports`'s
        stated one-scope-per-orchestrator pattern, and why that's not a
        correctness loss for this orchestrator specifically.

        This is the pipeline's longest stage by far: one `resolve_signal`
        call per staged row, each doing a real network round trip via
        `check_domain_reachable`, sequentially (Jira KAN-62, not
        concurrent; see `adr/0014-pipeline-entry-point-and-stage-failure-policy.md`'s
        Context section for why this run's actual behavior was traced
        before deciding that stage's failure policy). At real project
        volume this can run 30 minutes or more with no database write
        until the very end, so progress is logged periodically at INFO,
        naming the row last processed, precisely so a long run is
        visibly advancing rather than indistinguishable from a hang.
        Per-row detail beyond that stays at DEBUG
        (`huginn.elt.silver.resolution.check_domain_reachable`'s own
        docstring already explains why: naming every one of ~6,000+ checks
        at INFO would flood the log).
        """
        with self._repository:
            staged_signals = (
                self._repository.read_hn_postings()
                + self._repository.read_yc_listings()
            )

        total = len(staged_signals)
        resolved_records = []
        for processed, signal in enumerate(staged_signals, start=1):
            resolved_company_key, key_derivation = resolve_signal(
                signal.source, signal.stable_id, signal.website
            )
            if processed % _PROGRESS_LOG_INTERVAL == 0 or processed == total:
                logger.info(
                    "silver.resolved_signals resolve_all: processed %d of %d "
                    "(last: source=%s stable_id=%s)",
                    processed,
                    total,
                    signal.source,
                    signal.stable_id,
                )
            resolved_records.append(
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
                    key_derivation=key_derivation,
                    company_status=signal.company_status,
                    team_size=signal.team_size,
                    industries=signal.industries,
                    all_locations=signal.all_locations,
                    former_names=signal.former_names,
                    batch=signal.batch,
                )
            )

        written = 0
        with self._repository:
            for record in resolved_records:
                self._repository.upsert(record)
                written += 1

        logger.info("silver.resolved_signals resolve_all: %d written", written)
        return written

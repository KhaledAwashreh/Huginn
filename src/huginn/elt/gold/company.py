"""Company/CompanyHistory writer: wires apply_company_update
(huginn.elt.gold.dimensional) to Postgres. Jira KAN-40, ADR-0002,
architecture document section 4.3.
"""

from __future__ import annotations

import logging

from huginn.elt.gold.dimensional import apply_company_update
from huginn.elt.gold.ports import CompanyRepositoryPort

logger = logging.getLogger(__name__)


def write_company(
    repository: CompanyRepositoryPort, domain: str, new_values: dict
) -> None:
    """Read the current gold.company row for `domain` (None on first
    occurrence), apply `new_values` via apply_company_update, and write
    the result back. See ADR-0002 and `huginn.elt.gold.dimensional` for
    the Type 1/Type 2 history rule this wires to Postgres.

    Must be called from inside `with repository:` (see
    `CompanyWriter.write_all`); this function opens no connection of its
    own.
    """
    current = repository.get_company(domain)
    result = apply_company_update(current or {}, new_values)

    # No history on first occurrence: apply_company_update can't tell "no
    # row" from "row exists but the field was never set" (current.get(...)
    # reads None either way), and there's no prior version to supersede
    # when current is None. Acting on it would insert a company_history
    # row with company_id = NULL (current.get("id") on an empty dict),
    # violating that column's NOT NULL constraint.
    should_write_history = current is not None and result.history_snapshot is not None
    repository.upsert_company(
        domain, result.new_values, bump_current_since=should_write_history
    )

    if should_write_history:
        snapshot = result.history_snapshot
        repository.insert_history(
            company_id=snapshot["company_id"],
            domain=domain,
            snapshot=snapshot,
            valid_from=current["current_since"],
        )


class CompanyWriter:
    """Reads every domain-normalized silver.resolved_signals row and
    upserts gold.company via `write_company`. Jira KAN-40.

    Only domain-normalized rows: a placeholder key awaiting manual review
    (`huginn.elt.silver.resolution.KeyDerivation.UNRESOLVED`) is
    not a real company identity yet (architecture document section 6), so
    writing it into Company would put a synthetic "unresolved:..." value
    where the durable natural key belongs. Enforced by
    `CompanyRepositoryPort.read_domain_normalized_signals`'s own query, not
    here.

    Only `domain` and `name` are derivable from resolved_signals today:
    docs/entities.md's ResolvedSignal carries no business_sector,
    team_composition_signal, icp_filter_pass, or contact/location field.
    Those stay at their gold.company default until a future writer (Jira
    KAN-43, enrichment) has real data for them and calls `write_company`
    with a richer `new_values` dict.
    """

    def __init__(self, repository: CompanyRepositoryPort) -> None:
        self._repository = repository

    def write_all(self) -> int:
        """Upsert every distinct company found among domain-normalized
        signals, returning the count of companies written.

        `read_domain_normalized_signals` returns event grain (one row per
        original signal, per docs/entities.md's ResolvedSignal); the same
        domain can appear many times. Collapsing to one write per domain
        here, keeping the most recently resolved `company_name_raw`, saves
        the redundant read/write round-trips a company with N signals
        would otherwise cost, at no loss: gold.company only ever holds
        current state (ADR-0002), so only the last name would have
        survived anyway.
        """
        with self._repository:
            signals = self._repository.read_domain_normalized_signals()
            name_by_domain = {
                signal.domain: signal.company_name_raw for signal in signals
            }
            for domain, name in name_by_domain.items():
                write_company(self._repository, domain, {"name": name})
            written = len(name_by_domain)

        logger.info("gold.company write_all: %d written", written)
        return written

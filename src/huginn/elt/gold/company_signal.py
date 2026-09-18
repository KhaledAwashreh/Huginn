"""CompanySignal fact writer: wires silver.resolved_signals to
gold.company_signal. Jira KAN-41, ADR-0007, architecture document
section 4.3.
"""

from __future__ import annotations

import logging

from huginn.elt.gold.ports import CompanySignalRepositoryPort

logger = logging.getLogger(__name__)


class CompanySignalWriter:
    """Reads every domain-normalized signal already joined to its
    gold.company row and upserts one gold.company_signal row per signal.
    Jira KAN-41.

    Event grain, not collapsed (Global Constraint 2 of this plan; unlike
    CompanyWriter, which deliberately collapses to one row per domain):
    resolved_signals is already event grain and company_signal stays there.
    """

    def __init__(self, repository: CompanySignalRepositoryPort) -> None:
        self._repository = repository

    def write_all(self) -> int:
        """Upsert every domain-normalized signal's fact row, returning the
        count written. Idempotent per ADR-0007: re-running this after
        Silver's own every-run reprocessing updates existing rows in
        place rather than duplicating them.
        """
        with self._repository:
            facts = self._repository.read_signal_facts()
            for fact in facts:
                self._repository.upsert_signal(fact)
            written = len(facts)

        logger.info("gold.company_signal write_all: %d written", written)
        return written

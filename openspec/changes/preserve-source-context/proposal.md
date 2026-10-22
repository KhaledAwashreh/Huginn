## Why

Current staging drops HN engagement/location headers and EU listing attributes,
while YC context is selected into a single description. This can misrepresent
employment as service demand and prevents an honest evaluation of collected data.

## What Changes

- Preserve full normalized HN text and header/body boundaries in additive Silver
  context, without changing existing descriptions or current Gold projections.
- Preserve EU short/long descriptions, source country/place/tags, and selected
  YC summary/taxonomy/hiring observations in versioned source-keyed snapshots.
- Keep source observations distinguishable from processing time and support
  unresolved source identities without promoting them to confirmed companies.
- Add an offline/read-only audit path to compare outputs with stored Bronze and
  an explicit implementation-test-adjust loop using persisted data.
- Leave lifecycle guards and Gold promotion to sequenced follow-on changes.

## Capabilities

### New Capabilities

- `source-context-preservation`: Deterministic, versioned source context independent
  of company resolution, compatible with existing staging and matching.
- `source-context-audit`: Read-only real-data comparison, discrepancy reporting,
  and repeatable output acceptance checks.

### Modified Capabilities

None. The local main spec tree has no existing capability to amend. Existing
Gold/matchmaking behavior is deliberately outside this preservation change.

## Impact

Source-specific Silver parsers/loaders/repositories, additive Silver DDL,
BeautifulSoup helper reuse, source-context persistence, audit CLI, tests, and
runbooks. No new ML/vector dependencies, public API changes, Gold backfill,
identity reassignment, or operational match mutation.

Implementation baseline is commit `4cbabd8` or its verified successor, not the
older primary checkout. See `architecture-notes/client-opportunity-ranking-v0.1.md`
and `architecture-notes/client-opportunity-implementation-roadmap.md` for rationale,
follow-on dependencies, and review gates.

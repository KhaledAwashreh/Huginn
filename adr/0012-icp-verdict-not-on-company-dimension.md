# 0008: The ICP filter verdict does not belong on the shared company dimension

Status: Accepted
Date: 2026-09-25
Deciders: Khaled Awashreh

## Context and Problem Statement

`gold.company` carried `icp_filter_pass BOOLEAN NOT NULL DEFAULT false`, and
`gold.company_history` carried it as one of ADR-0002's three Type 2 tracked
fields. The architecture document justified it as "a tracked attribute on the
row, not a gate on whether the row exists, so a company that later stops
passing keeps its record" (section 4.3), and as the precondition for the
team-composition heuristic, which runs "only on companies that already passed
the ICP filter".

The justification is sound and the column is still wrong, because a single
un-namespaced boolean cannot hold a per-user verdict. An ICP is by definition
one user's description of who they want to sell to, and the same architecture
document commits at section 2 to "a domain model that's multi-user from day
one, even though exactly one user exists right now. Phase 2 becomes additive,
not a rebuild." Those two commitments cannot both hold in one boolean on a
shared row. Once a filter is implemented, the column can only mean "passes
*someone's* ICP", which would put companies into user B's digest that fail
user B's own filter, or "passes *the* ICP", which is a singleton pretending to
be shared state and would need a migration rather than the additive change the
multi-user commitment promises.

Reading the result cold, the column looks like a missing feature rather than a
deliberate absence, which is the specific reason this ADR exists.

## Decision Drivers

1. The ICP is per-user; the ELT Gold layer is source-agnostic and knows nothing
   about users. A user's verdict on a company is a property of the
   relationship, not of the company.
2. Architecture document section 2 requires Phase 2 to be additive. A
   single-valued boolean on a shared dimension forces a migration.
3. `BOOLEAN NOT NULL DEFAULT false` cannot distinguish "evaluated and failed"
   from "never evaluated", while section 4.3 promises `Company` "covers every
   company Silver has resolved and evaluated against the filter at least once".
4. `operational.match` already has the right grain for a per-user verdict: it
   carries `user_id` and `company_id` as separate foreign keys, and the ER
   diagram labels the relationship "shared pool, matched per user", so the
   verdict belongs in the operational schema, written by the matching step
   rather than by the ELT pipeline. Note that this is a grain, not yet an
   enforced key: the table's only unique constraint is its `id` primary key,
   and nothing stops two rows for the same user and company. That gap is the
   matching step's to close, and it is a reason the verdict cannot be inferred
   from this table today, not a reason to put it on `gold.company`.

## Considered Options

1. Remove `icp_filter_pass` from the Gold dimension entirely (chosen)
2. Keep it as a nullable boolean, tri-state, on `gold.company`
3. Keep it and add a parallel per-user table
4. Keep it, unchanged

## Decision Outcome

Chosen option: 1. `icp_filter_pass` is removed from `gold.company` and
`gold.company_history`, and from `TYPE_2_TRACKED_FIELDS`, leaving
`business_sector` and `team_composition_signal` as the Type 2 tracked fields.
Where the per-user verdict belongs is left to the matching step (Jira KAN-18),
which is the layer that owns users and already has the right grain.

### Consequences

1. Good: the Gold dimension stops implying a single user's verdict, so Phase 2
   stays additive as the architecture document requires.
2. Good: the "never evaluated" versus "evaluated and failed" ambiguity
   disappears, because evaluation state becomes a fact about a row that either
   exists or does not, in the operational schema, rather than a boolean that
   has to encode it.
3. Good: one fewer Type 2 field means one fewer source of spurious
   `company_history` rows, since a per-user verdict is high-churn and would
   have written history rows for changes that are not changes to the company.
4. Bad: there is no longer any record on the dimension that a company was ever
   evaluated, so "which companies have we looked at" needs the matching step's
   tables. Acceptable, since that is the layer that performs the evaluation.
5. Bad: `company_history` narrows to two tracked fields, and of those two
   `business_sector` is the only one with a writer, so a sector change is
   now the sole common trigger for a history row. It is not a rare one:
   `business_sector` is populated on 4,337 of the 4,423 live `gold.company`
   rows, so a company whose `silver.resolved_signals.industries` differ
   between two `write_all` runs writes a row.
6. Bad: the history table is empty today, and nothing in this decision is
   what keeps it that way. `team_composition_signal` has no writer anywhere
   in the tree, but that is not the reason: `business_sector` alone fills
   the table without it. The reason is that no re-run has yet observed a
   differing `business_sector` for a company row that already exists, which
   is a property of the data so far rather than a guarantee. An unwritten
   field and an unchanged field are indistinguishable from the row count,
   so the two are worth keeping apart.

## Pros and Cons of the Options

### Option 1: Remove from the Gold dimension (chosen)

1. Good: no per-user data on a user-agnostic layer.
2. Good: nothing in the ELT pipeline writes it, so the removal is a pure
   deletion with no behavioural change; the column was `false` on all 4,423
   live rows and had never been `true`.
3. Bad: the "attribute not a gate" rationale from architecture document
   section 4.3 now has no column to apply to, so that sentence needs rewording
   rather than leaving to be read as an unmet intention.

### Option 2: Nullable or tri-state boolean on `gold.company`

1. Good: keeps the evaluation record on the dimension.
2. Bad: still single-valued. Tri-stating `unknown`/`fail`/`pass` fixes the
   ambiguity in driver 3 but leaves drivers 1 and 2 untouched, so a second user
   still needs a migration. It also leaves a per-user concept on a layer that
   does not know about users.

### Option 3: Keep it and add a parallel per-user table

1. Good: the per-user grain is explicit.
2. Bad: two places record a verdict, and the dimension copy would have to be
   kept consistent with the per-user one. Strictly more complexity than
   option 1 for a column that has never held a non-default value.

### Option 4: Keep it, unchanged

1. Good: no work.
2. Bad: knowingly ships a column that cannot be correct for more than one user,
   against an explicit multi-user commitment.

## Related

1. `docs/architecture.md` section 2, the multi-user-from-day-one commitment,
   and section 4.3, whose "tracked attribute, not a gate" rationale this
   decision makes moot.
2. ADR-0002, the current-plus-history split. Its text describes "a Type 2
   tracked field" generically and never enumerates the three, so the decision
   changes the implementation without superseding that ADR.
3. `db/schema/operational.sql`, `operational.match` and
   `operational.users.icp_profile`, the grain that fits a per-user verdict.
   The pair is not yet uniquely constrained; see Decision Driver 4.
4. Jira KAN-18, the matching step, which owns where the verdict is computed and
   stored.
5. Jira KAN-20, the open column-by-column Type 1/Type 2 classification, of
   which this settles one column.

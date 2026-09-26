# 0009: The gold.company write has two shapes, and `name` decides which

Status: Accepted
Date: 2026-09-26
Deciders: Khaled Awashreh

## Context and Problem Statement

`build_upsert_query` is not a single upsert. It emits one of two statements
depending on whether `name` is a key in `new_values`, and
`PostgresCompanyRepository.upsert_company` raises `ValueError` when the
update-only shape matches no row. Read cold, all three look like defects: a
method named "upsert" that sometimes does not insert, and a write that can fail
for a reason having nothing to do with the data it was handed.

None of it is accidental, and none of it is visible at the call site. The
constraint is that `name` is `gold.company`'s only NOT NULL column besides
`domain` and has no default (`db/schema/gold.sql` lines 17 to 18). Postgres
validates NOT NULL before `ON CONFLICT` is considered, so one statement cannot
both insert a row and skip a column the caller does not have. Any single
statement that inserts must supply a name.

The alternative to two shapes is not "one correct upsert". Every way of
collapsing them either writes a name the caller did not supply, or gives up
the single-statement property.

## Decision Drivers

1. A caller supplying only enrichment values, such as a sector or a headcount,
   must not cause a company to be invented, and must not be able to create a
   row whose name is a stand-in.
2. The insert-or-update path must stay one statement, so a concurrent writer
   cannot slip between a read and a write.
3. A write that creates nothing must not return as though it had.
4. Only `domain` may reach the `ON CONFLICT` target or the `WHERE` clause, and
   only as a bind parameter (`BEST_PRACTICES.md` section 8.1).

## Considered Options

1. Two shapes, selected by presence of the `name` key, and an explicit
   `ValueError` on an update-only write that matched no row.
2. One always-inserting statement that binds `domain` or a placeholder when the
   caller has no real name.
3. One always-inserting statement, preceded by a `SELECT` to decide whether a
   row exists.

## Decision Outcome

Chosen option: 1, two shapes. A caller that supplies `name` gets
`INSERT ... ON CONFLICT (domain) DO UPDATE`, which inserts or updates in one
statement. A caller that does not gets `UPDATE ... WHERE domain = %s`, which
cannot violate NOT NULL because it attempts no insert, and raises rather than
reporting a success that wrote nothing.

### Consequences

1. Good: the name a lead digest shows is never a fabricated value, and a
   caller cannot accidentally create a company by enriching a domain it has
   never seen.
2. Good: the insert path keeps the race-free single-statement upsert.
3. Good: `bump_current_since` stays unobservable on insert, because a fresh row
   already receives `current_since = now()` from the column default
   (`db/schema/gold.sql` line 96).
4. Bad: the method named `upsert_company` has a mode in which it does not
   upsert. The name understates it.
5. Bad: the failure mode is a `ValueError` at runtime rather than a type or
   signature error at the call site. `new_values` is a `dict`, so the compiler
   cannot enforce which shape a caller is in.
6. Bad: the two-shape branch exists for a caller that does not exist yet. The
   enrichment writer tracked as Jira KAN-43 is its intended user; today's
   `CompanyWriter` always supplies a name, so the update-only shape is
   currently unreachable through the production path.

## Pros and Cons of the Options

### Option 1: two shapes, decided by `name`

1. Good: never writes a name the caller did not supply.
2. Good: keeps the insert path to one statement.
3. Good: a write that creates nothing fails loudly.
4. Bad: two shapes to test and to keep documented.
5. Bad: the branch is unexercised by the current production caller.

### Option 2: bind `domain` or a placeholder as the name

1. Good: one statement, one shape, no branch.
2. Bad: writes a fabricated value into the column the product shows as a
   company's name, and does so silently, with no signal that enrichment of an
   unknown domain created a company.

### Option 3: `SELECT` first, then decide insert or update

1. Good: one call site, no branch on the write statement itself.
2. Bad: two round trips, and a window in which a concurrent writer can insert
   or update the same domain between the read and the write, reintroducing
   exactly the race the `ON CONFLICT` upsert exists to close.
3. Bad: still needs option 1's `ValueError`, because the read can be stale by
   the time the write lands.

## Related

1. `docs/architecture.md` section 4.3, the Gold layer.
2. ADR-0002, the current-plus-history split that `current_since` and
   `bump_current_since` belong to.
3. `db/schema/gold.sql` lines 17 to 18 and line 96, the `name` and `domain`
   NOT NULL columns and the `current_since` default.
4. Jira KAN-43, the enrichment writer that is the intended caller of the
   update-only shape.
5. Source: the code review of 2026-09-25, finding GOLD-01, held as personal
   reference material outside this repository. The reasoning was pulled into
   this record rather than linked, per `adr/README.md`.

# Architecture Decision Records

MADR format (`template.md`). Full structure every time: Context and Problem Statement, Decision Drivers, Considered Options, Decision Outcome with Consequences, Pros and Cons per option, Related.

Naming: `NNNN-kebab-case-title.md`, zero-padded, sequential. Never reused even if a later ADR supersedes an earlier one.

Status values:

1. `Proposed`: not yet acted on.
2. `Accepted`: in effect.
3. `Superseded by NNNN`: a later ADR replaced it. Do not delete the old one; it is still the record of why the prior choice was made.
4. `Deprecated`: no longer followed, nothing replaced it.

When to write one: an architectural decision with a real alternative that was seriously weighed, especially one where the outcome would otherwise look like an inconsistency or a mistake to someone reading the result cold (see ADR-0001 for exactly that case). Not every implementation detail needs one. Routine, obvious choices do not.

Where the reasoning already exists elsewhere (an entry in `architecture-notes/`, a Jira ticket, a prior session's transcript), the ADR is still the canonical record. Pull the reasoning into the ADR's own sections rather than just linking out to it, and note the source under Related.

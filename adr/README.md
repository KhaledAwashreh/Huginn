# Architecture Decision Records

MADR format (`template.md`) — full structure every time: Context and Problem Statement, Decision Drivers, Considered Options, Decision Outcome with Consequences, Pros and Cons per option, Related.

**Naming:** `NNNN-kebab-case-title.md`, zero-padded, sequential — never reused even if a later ADR supersedes an earlier one.

**Status values:** `Proposed` (not yet acted on) → `Accepted` (in effect) → `Superseded by NNNN` (a later ADR replaced it — don't delete the old one, it's still the record of why the prior choice was made) or `Deprecated` (no longer followed, nothing replaced it).

**When to write one:** an architectural decision with a real alternative that was seriously weighed, especially one where the outcome would otherwise look like an inconsistency or a mistake to someone reading the result cold (see ADR-0001 for exactly that case). Not every implementation detail needs one — routine, obvious choices don't.

**Where the reasoning already exists elsewhere** (an entry in `architecture-notes/`, a Jira ticket, this session's transcript), the ADR is still the canonical record — pull the reasoning into the ADR's own sections rather than just linking out to it, and note the source under Related.

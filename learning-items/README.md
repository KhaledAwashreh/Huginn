# Learning items

Tracks technical knowledge gaps surfaced while building Huginn, one file per
topic (`template.md`): Python-language/tooling concepts new to the project's
engineer (a Java/C# background), and general technical/domain research the
team hasn't studied yet (an algorithm, a library, a pattern, a candidate
source's API). Local for now; several items already exist as Jira tickets
under epic KAN-16, their `Jira:` field is filled in; new items get synced
later.

Naming: `kebab-case-topic.md`, no numbering, topics aren't sequential or
dependent on each other the way ADRs are.

Status values:

1. `Backlog`: surfaced, not yet worked through.
2. `Learning`: actively being read/practiced.
3. `Done`: understood well enough that this file is a reference, not a
   to-do.

When to add one: a real knowledge gap, not a decision. Huginn's own
architecture/design decisions, and open decisions still needing a call
(legal risk acceptance, unresolved design work), don't belong here, those
stay in `adr/` or as regular Jira tickets under KAN-16.

# 0001: Split global configuration between CLAUDE.md and lazy-loaded skills

Status: Accepted
Date: 2026-09-05
Deciders: Khaled Awashreh (with Claude Sonnet 5 assisting)

## Context and Problem Statement

A writing style guide was extracted from a work Claude Code setup: language and communication rules, plus 10 detailed document templates (bug report, ticket, RCA, handoff, QA handoff, release notes, resolution summary, engineering ticket comment, support-facing summary, validation report). It needed a home in the global Claude Code configuration.

First attempt: wrote all of it into `~/.claude/CLAUDE.md`, which loads into every conversation regardless of task. Second attempt: moved everything into a skill and left CLAUDE.md empty, which also removed the general-purpose behavioral instructions and the cross-project navigation index that should apply to every task, not just document writing. Neither was right.

## Decision Drivers

1. CLAUDE.md content costs context on every turn of every conversation, regardless of relevance to the task.
2. Skills load only when their description matches the current task.
3. Some content (verification discipline, communication tone, cross-project navigation) applies to nearly every conversation.
4. Other content (10 document templates) only applies when actually writing one of those document types.
5. An empty CLAUDE.md removes general-purpose instructions along with the task-specific bulk. That is a separate mistake, not a fix for the first one.

## Considered Options

1. Everything in CLAUDE.md (first attempt)
2. Everything in a skill, CLAUDE.md empty (second attempt)
3. Split by relevance: general content in CLAUDE.md, task-specific templates in a lazy-loaded skill (chosen)

## Decision Outcome

Chosen option: 3, split by relevance. CLAUDE.md and skills solve different problems. CLAUDE.md holds what should be true on every turn: verification discipline, communication tone, a navigation index of active projects and available skills. A skill holds what should load only when the task calls for it: the 10 document templates only matter when something is actually being written in one of those formats, and loading them unconditionally spends context on every unrelated turn for no benefit.

### Consequences

1. CLAUDE.md stays small. Every conversation pays a fixed, minimal cost for it.
2. The technical-writing skill's full template library is available at zero cost until a task triggers it.
3. General behavioral principles apply consistently across all work, not only document writing.
4. Content now lives in two places. A future addition has to be classified correctly instead of defaulting to one location.
5. A poorly written skill description risks not triggering when it should. CLAUDE.md content carries no such risk since it is always loaded.

## Pros and Cons of the Options

### Option 1: Everything in CLAUDE.md

1. Good: no trigger-matching risk. The content is guaranteed present whenever needed.
2. Good: one place to look for any instruction.
3. Bad: every conversation pays the full context cost of 10 document templates even when the task has nothing to do with writing one.
4. Bad: mixes always-relevant and task-specific instructions in one file. Harder to tell what is actually load-bearing for a given task.

### Option 2: Everything in a skill, CLAUDE.md empty

1. Good: CLAUDE.md's context cost drops to zero.
2. Bad: general-purpose instructions only apply when the skill happens to trigger, even though they should apply to every task.
3. Bad: no always-on navigation index. A fresh session has no cheap way to know what projects exist or where prior context lives.

### Option 3: Split by relevance (chosen)

1. Good: each piece of content lives where its usage pattern says it should. Constant and always-relevant in CLAUDE.md. Occasional and task-specific in a skill.
2. Good: updating either file does not risk breaking the other's purpose.
3. Bad: requires a judgment call for every future addition about which bucket it belongs in, instead of one default location.

## Related

1. `~/.claude/CLAUDE.md`: the current, post-decision content.
2. `~/.claude/skills/technical-writing/SKILL.md`: the lazy-loaded template library this decision moved out of CLAUDE.md.
3. `Huginn/adr/README.md`: the MADR convention this ADR follows.

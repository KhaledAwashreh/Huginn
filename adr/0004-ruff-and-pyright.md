# 0004: Ruff for linting/formatting, pyright for type checking

Status: Accepted (adoption deferred)
Date: 2026-09-08
Deciders: Khaled Awashreh (with Claude Sonnet 5 assisting)

## Context and Problem Statement

Huginn's code has carried type hints throughout since the first commit, but nothing checks them, and no formatter or linter enforces style. `CLAUDE.md` flagged this as an open gap rather than a decision, deliberately, to avoid picking tooling unprompted. The decision-maker's engineering background is Java/C#, where the compiler bundles style checking, type checking, and build validation into one step; Python splits these into separate, optional tools, and a choice has to be made explicitly for each.

## Decision Drivers

1. The Python community has converged on Ruff (Rust-based) as the default for style and lint checks, replacing the older Black/isort/Flake8 three-tool combination.
2. A type checker is a separate, still-open choice between mypy (the original, most widely adopted, slower) and pyright (Microsoft's, 2-5x faster, the engine behind VS Code's Pylance extension).
3. The decision-maker is new to Python and benefits from immediate, in-editor feedback that resembles what a Java/C# IDE already gives for free, rather than a separate CI-only check discovered later.
4. Neither tool has any existing configuration or investment in this codebase yet, so there is no migration cost weighing toward either option.

## Considered Options

For linting/formatting, Ruff was not a genuinely contested choice (it has functionally superseded the tools it replaces); the real fork is the type checker:

1. mypy
2. pyright (chosen)

## Decision Outcome

Chosen option: Ruff for lint and format (uncontested), pyright for type checking. pyright's speed and its identity as the engine behind Pylance make it the better fit for a contributor still building Python fluency who benefits from live in-editor type errors, the closest available equivalent to a Java/C# compiler's immediate feedback.

Adoption itself (installing the packages, adding configuration, running them in CI) is deliberately deferred as a low-priority item, tracked separately from this decision. This ADR records the choice, not the rollout.

### Consequences

1. Good: fast local feedback loop once adopted, especially valuable while still learning the language.
2. Good: Ruff alone replaces three older tools, minimizing the number of dev dependencies to reason about.
3. Bad: pyright's third-party plugin/stub ecosystem is smaller than mypy's older, more established one; relevant only if a future dependency ships mypy-specific type stubs with no pyright equivalent.
4. Neutral: until adoption happens, this decision has no effect on the codebase. See `CLAUDE.md` code standard 7 for the deferred-adoption status.

## Pros and Cons of the Options

### Option 1: mypy

1. Good: the original, most mature, widest third-party plugin ecosystem.
2. Bad: noticeably slower than pyright, especially on incremental re-checks.
3. Bad: not the engine behind the most common free in-editor Python type-checking extension (Pylance), so it needs its own separate editor integration.

### Option 2: pyright (chosen)

1. Good: 2-5x faster than mypy.
2. Good: identical engine to Pylance, so a contributor using VS Code already gets this checking live, with zero extra editor configuration.
3. Bad: smaller third-party stub/plugin ecosystem than mypy's.

## Related

1. `CLAUDE.md` code standard 7: records the deferred-adoption status.
2. `BEST_PRACTICES.md` sections 1 and 2: general community context on Ruff and the mypy/pyright landscape.
3. Confluence, "Learning: Python Linting and Type Checking" (Huginn space, page ID 1277953): a plain-language explainer of what these tools do, written for the decision-maker's Java/C# background.

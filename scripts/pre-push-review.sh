#!/usr/bin/env bash
# Deterministic version of CLAUDE.md's "Before pushing" checklist. Installed
# as .git/hooks/pre-push (not versioned by git; see the one-time setup note
# in CLAUDE.md) so these checks run on every `git push` in this repo,
# independent of whether the pusher (human or Claude Code) remembers to run
# them by hand.
#
# The test and lint commands are hard gates, matching CI. AI review is handled
# by the explicit pre-MR skill so a push stays deterministic and does not
# unexpectedly transmit the diff to a service.
set -uo pipefail

# A dirty working tree (uncommitted changes) isn't necessarily what's
# actually about to be pushed: git push sends committed objects, not
# working-tree state. Refuse to run checks against a state that might not
# match the push, rather than let a pass here mean nothing.
if [ -n "$(git status --porcelain)" ]; then
    echo "Working tree has uncommitted changes. Commit or stash them first" >&2
    echo "so these checks test exactly what's about to be pushed. Push blocked." >&2
    exit 1
fi

fail=0

echo "== uv run pytest =="
if ! uv run pytest; then
    echo "pytest failed." >&2
    fail=1
fi

echo
echo "== uv run ruff check . =="
if ! uv run ruff check .; then
    echo "ruff check failed." >&2
    fail=1
fi

echo
echo "== uv run ruff format --check . =="
if ! uv run ruff format --check .; then
    echo "ruff format --check failed." >&2
    fail=1
fi

if [ "$fail" -ne 0 ]; then
    echo
    echo "One or more hard checks failed above. Push blocked." >&2
    exit 1
fi

exit 0

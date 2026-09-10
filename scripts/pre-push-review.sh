#!/usr/bin/env bash
# Deterministic version of CLAUDE.md's "Before pushing" checklist. Installed
# as .git/hooks/pre-push (not versioned by git; see the one-time setup note
# in CLAUDE.md) so these checks run on every `git push` in this repo,
# independent of whether the pusher (human or Claude Code) remembers to run
# them by hand.
#
# Steps 1 and 2 below are the exact commands CLAUDE.md's "Before pushing"
# section names. Step 1 is a hard gate: a failure here blocks the push,
# matching CI (.github/workflows/ci.yml), which runs the same checks. Step 2
# (CodeRabbit) is deliberately NOT a gate: CLAUDE.md states its severities
# aren't one ("the same diff reviewed twice can surface different findings,
# so its exit code is never checked and it never fails a build") — this
# script honors that by always printing its findings but never failing the
# push on them. Its job is to make the findings impossible to miss, not to
# block on them.
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

echo
echo "== coderabbit review --agent --base master =="
if command -v coderabbit >/dev/null 2>&1; then
    coderabbit review --agent --base master || true
else
    echo "coderabbit CLI not found on PATH." >&2
    echo "Install it: https://docs.coderabbit.ai/cli (or see CLAUDE.md's" >&2
    echo "'Before pushing' section). Push blocked: this script's whole job is" >&2
    echo "making sure this check actually runs, not making it optional." >&2
    exit 1
fi

exit 0

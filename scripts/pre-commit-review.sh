#!/usr/bin/env bash
# Fast, deterministic checks for the local pre-commit hook. AI review belongs
# to the explicit pre-MR workflow; this hook must stay quick and offline.
set -uo pipefail

fail=0

echo "== git diff --cached --check =="
if ! git diff --cached --check; then
    echo "staged whitespace errors found. Commit blocked." >&2
    fail=1
fi

echo "== uv run ruff check . =="
if ! uv run ruff check .; then
    echo "ruff check failed. Commit blocked." >&2
    fail=1
fi

echo
echo "== uv run ruff format --check . =="
if ! uv run ruff format --check .; then
    echo "ruff format --check failed. Commit blocked." >&2
    fail=1
fi

if [ "$fail" -ne 0 ]; then
    exit 1
fi

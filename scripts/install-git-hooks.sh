#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
hooks_dir="$(git rev-parse --path-format=absolute --git-path hooks)"

if [ ! -d "$hooks_dir" ]; then
    echo "Git hooks directory does not exist: $hooks_dir" >&2
    exit 1
fi

install -m 0755 "$repo_root/scripts/pre-commit-review.sh" "$hooks_dir/pre-commit"
install -m 0755 "$repo_root/scripts/pre-push-review.sh" "$hooks_dir/pre-push"

echo "Installed pre-commit and pre-push hooks in $hooks_dir"

#!/usr/bin/env bash
set -euo pipefail

force=0
if [ "${1:-}" = "--force" ]; then
    force=1
elif [ "$#" -ne 0 ]; then
    echo "Usage: $0 [--force]" >&2
    exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
hooks_dir="$(git rev-parse --path-format=absolute --git-path hooks)"

if [ ! -d "$hooks_dir" ]; then
    echo "Git hooks directory does not exist: $hooks_dir" >&2
    exit 1
fi

for hook in pre-commit pre-push; do
    target="$hooks_dir/$hook"
    source="$repo_root/scripts/$hook-review.sh"
    if [ ! -e "$target" ]; then
        continue
    fi
    if cmp -s "$source" "$target"; then
        continue
    fi
    if [ "$force" -ne 1 ]; then
        echo "Refusing to overwrite existing hook: $target" >&2
        echo "Use --force to back it up and replace it explicitly." >&2
        exit 1
    fi
    backup="$target.bak"
    if [ -e "$backup" ]; then
        echo "Refusing to overwrite existing hook backup: $backup" >&2
        exit 1
    fi
    cp -p "$target" "$backup"
    echo "Backed up existing hook to $backup"
done

install -m 0755 "$repo_root/scripts/pre-commit-review.sh" "$hooks_dir/pre-commit"
install -m 0755 "$repo_root/scripts/pre-push-review.sh" "$hooks_dir/pre-push"

echo "Installed pre-commit and pre-push hooks in $hooks_dir"

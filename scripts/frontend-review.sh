#!/usr/bin/env bash
# Conditional browser checks shared by the repository's installed Git hooks.
set -uo pipefail

mode="${1:-}"
repo_root="$(git rev-parse --show-toplevel)" || exit 1
cd "$repo_root"

changed_paths=()

collect_staged_paths() {
    while IFS= read -r -d '' path; do
        changed_paths+=("$path")
    done < <(git diff --cached --name-only -z -- frontend)
}

collect_pushed_paths() {
    local local_ref local_oid remote_ref remote_oid base_ref base path diff_file

    while read -r local_ref local_oid remote_ref remote_oid; do
        if [ -z "${local_ref:-}${local_oid:-}${remote_ref:-}${remote_oid:-}" ]; then
            continue
        fi
        if [ -z "${local_ref:-}" ] || [ -z "${local_oid:-}" ] || [ -z "${remote_ref:-}" ] || [ -z "${remote_oid:-}" ]; then
            echo "Cannot inspect malformed pre-push ref update; push blocked because changed paths are unknown." >&2
            return 1
        fi
        [[ "$local_oid" =~ ^0+$ ]] && continue
        if ! git cat-file -e "$local_oid^{commit}" 2>/dev/null; then
            echo "Cannot diff pushed commits: local commit $local_oid is unavailable." >&2
            return 1
        fi

        if [[ "$remote_oid" =~ ^0+$ ]]; then
            base_ref="${HUGINN_PRE_PUSH_BASE_REF:-origin/master}"
            if ! git rev-parse --verify --quiet "$base_ref^{commit}" >/dev/null; then
                echo "Cannot determine the base for new branch $remote_ref." >&2
                echo "Fetch the target branch or set HUGINN_PRE_PUSH_BASE_REF to its local ref, then retry." >&2
                return 1
            fi
            if ! base="$(git merge-base "$local_oid" "$base_ref")"; then
                echo "Cannot find a common base between $local_ref and $base_ref." >&2
                echo "Fetch the target branch or set HUGINN_PRE_PUSH_BASE_REF to its local ref, then retry." >&2
                return 1
            fi
        else
            if ! git cat-file -e "$remote_oid^{commit}" 2>/dev/null; then
                echo "Cannot diff pushed commits: remote commit $remote_oid is unavailable." >&2
                echo "Fetch the remote branch and retry; frontend checks cannot be skipped when the changed paths are unknown." >&2
                return 1
            fi
            base="$remote_oid"
        fi

        if ! diff_file="$(mktemp "${TMPDIR:-/tmp}/huginn-push-paths.XXXXXX")"; then
            echo "Cannot create a temporary file to inspect pushed paths." >&2
            return 1
        fi
        if ! git diff --name-only -z "$base" "$local_oid" >"$diff_file"; then
            rm -f "$diff_file"
            echo "Cannot diff pushed commits $base and $local_oid; push blocked because changed paths are unknown." >&2
            return 1
        fi
        while IFS= read -r -d '' path; do
            changed_paths+=("$path")
        done <"$diff_file"
        rm -f "$diff_file"
    done
}

check_runtime() {
    local expected_node expected_npm actual_node actual_npm

    if [ ! -f frontend/.node-version ] || [ ! -f frontend/package.json ] || [ ! -f frontend/package-lock.json ]; then
        echo "Frontend toolchain files are missing. Restore frontend/.node-version, package.json, and package-lock.json." >&2
        return 1
    fi
    expected_node="$(<frontend/.node-version)"
    expected_npm="$(sed -nE 's/.*"packageManager":[[:space:]]*"npm@([^"]+)".*/\1/p' frontend/package.json)"
    if [ -z "$expected_node" ] || [ -z "$expected_npm" ]; then
        echo "Cannot read the exact Node/npm pins from frontend/.node-version and frontend/package.json." >&2
        return 1
    fi
    if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
        echo "Frontend checks require Node $expected_node and npm $expected_npm on PATH." >&2
        echo "Install the pinned versions, then run npm --prefix frontend ci." >&2
        return 1
    fi
    actual_node="$(node --version 2>/dev/null || true)"
    actual_npm="$(npm --version 2>/dev/null || true)"
    if [ "$actual_node" != "v$expected_node" ] || [ "$actual_npm" != "$expected_npm" ]; then
        echo "Frontend checks require Node v$expected_node and npm $expected_npm; found Node ${actual_node:-missing} and npm ${actual_npm:-missing}." >&2
        echo "Select the pinned runtime, then run npm --prefix frontend ci. The hook will not install packages." >&2
        return 1
    fi
    if [ ! -x frontend/node_modules/.bin/eslint ] || [ ! -x frontend/node_modules/.bin/prettier ]; then
        echo "Frontend dependencies are missing. Run npm --prefix frontend ci; the hook will not install packages." >&2
        return 1
    fi
}

run_pre_commit_checks() {
    local fail=0
    if ! check_runtime; then return 1; fi
    if ! npm --prefix frontend run lint; then
        echo "Frontend lint failed." >&2
        fail=1
    fi
    if ! npm --prefix frontend run format:check; then
        echo "Frontend formatting check failed." >&2
        fail=1
    fi
    return "$fail"
}

run_pre_push_checks() {
    local path needs_check=0 needs_browser=0 fail=0
    for path in "${changed_paths[@]}"; do
        case "$path" in
            frontend/*|scripts/export-management-openapi.py|src/huginn/management/*|src/huginn/pipeline_control/*)
                needs_check=1
                ;;
        esac
        case "$path" in
            frontend/src/*|\
                frontend/tests/e2e/*|\
                frontend/index.html|\
                frontend/vite.config.ts|\
                frontend/playwright.config.ts|\
                src/huginn/management/presentation/api/routers/sessions.py|\
                src/huginn/management/presentation/api/static_assets.py|\
                src/huginn/management/presentation/api/dependencies/browser_origin.py|\
                src/huginn/management/application/services/authentication.py|\
                src/huginn/management/application/services/current_session_service.py|\
                src/huginn/management/security/csrf.py|\
                src/huginn/management/config.py|\
                tests/browser_fixture.py|\
                tests/postgres_harness.py)
                needs_browser=1
                ;;
        esac
    done

    if [ "$needs_check" -eq 0 ]; then
        echo "No frontend or management/pipeline API schema paths changed; no Node checks required."
        return 0
    fi
    if ! check_runtime; then return 1; fi

    if ! npm --prefix frontend run check; then
        echo "Frontend/schema checks failed. Push blocked." >&2
        fail=1
    fi
    if [ "$needs_browser" -eq 1 ]; then
        if [ ! -x frontend/node_modules/.bin/playwright ]; then
            echo "Playwright dependency is missing. Run npm --prefix frontend ci." >&2
            fail=1
        elif ! npm --prefix frontend run test:e2e; then
            echo "Browser checks failed. If Chromium is missing, install it manually with npm --prefix frontend exec -- playwright install chromium; this hook never installs browsers." >&2
            fail=1
        fi
    fi
    return "$fail"
}

case "$mode" in
    pre-commit)
        collect_staged_paths
        [ "${#changed_paths[@]}" -gt 0 ] || exit 0
        run_pre_commit_checks
        ;;
    pre-push)
        if ! collect_pushed_paths; then exit 1; fi
        run_pre_push_checks
        ;;
    *)
        echo "Usage: $0 {pre-commit|pre-push}" >&2
        exit 2
        ;;
esac

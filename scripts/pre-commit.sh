#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

uv_run_help="$(uv run --help)"
run_uv() {
    if [[ "$uv_run_help" == *"--no-install-project"* ]]; then
        uv run --no-install-project --no-build "$@"
    else
        uv run "$@"
    fi
}

echo "Running Ruff..."
run_uv ruff check .

echo "Running tests..."
run_uv pytest

echo "Pre-commit checks passed."

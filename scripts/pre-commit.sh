#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

echo "Running Ruff..."
uv run --no-project --no-build ruff check .

echo "Running tests..."
uv run --no-project --no-build pytest

echo "Pre-commit checks passed."

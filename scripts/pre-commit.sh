#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

echo "Running Ruff..."
uv run ruff check .

echo "Running tests..."
uv run pytest

echo "Pre-commit checks passed."

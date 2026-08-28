# AGENTS.md

## Project overview

`better-cov` is a Python CLI whose core implementation uses the standard library to compute a function-level coverage score weighted by importance indicators. It consumes Cobertura XML, locates Python source files, computes weighted and raw coverage, prints a terminal report, and can export JSON or Markdown. Pytest, pytest-cov, and Ruff are used for project development and verification.

## Environment

- Use Python 3.12 for local development (`.python-version`).
- Keep compatibility with Python 3.10+ as declared in `pyproject.toml`.
- Use `uv` for dependency and command management.
- Install or synchronize the environment with `uv sync`.
- Run project commands through `uv run`.

## Repository layout

- `better_cov/cli.py`: argument parsing, path resolution, and exit codes.
- `better_cov/parsers/cobertura.py`: Cobertura parsing and AST-based function extraction.
- `better_cov/indicators/`: importance indicator interface and implementations.
- `better_cov/scorer.py`: weighted coverage calculation and result models.
- `better_cov/reporter.py`: console, JSON, and Markdown reports.
- `.githooks/pre-commit`: versioned Git hook entry point.
- `scripts/pre-commit.sh`: Ruff and test checks run by the pre-commit hook.
- `action.yml`: composite GitHub Action integration.
- `.github/workflows/release.yml`: tagged PyPI release workflow.

## Development commands

```bash
uv sync
uv run ruff check .
uv run python -m better_cov --help
uv run pytest
uv build
```

Tests live under `tests/` and use `test_*.py` names. Run the full suite with `uv run pytest`.

## Pre-commit hook

The repository includes a versioned native Git hook in `.githooks/pre-commit`. It delegates to `scripts/pre-commit.sh`, which runs Ruff and the complete test suite. Enable it once per clone with:

```bash
git config core.hooksPath .githooks
```

Run the checks manually with `./scripts/pre-commit.sh`.

To exercise the CLI with a coverage report:

```bash
uv run pytest --cov=better_cov --cov-report=xml:coverage.xml
uv run better-cov --coverage-xml coverage.xml --source-dirs better_cov
```

## Implementation conventions

- Use `from __future__ import annotations` in Python modules.
- Prefer the standard library; do not add a runtime dependency unless the feature clearly requires it.
- Use type hints on public and internal function signatures.
- Use `pathlib.Path` for filesystem operations.
- Use dataclasses for structured parser, scoring, and report data.
- Keep CLI concerns in `cli.py`, parsing in `parsers/`, importance logic in `indicators/`, scoring in `scorer.py`, and presentation/export in `reporter.py`.
- Keep scores normalized to the `0.0`–`1.0` range internally; convert to percentages only at reporting boundaries.
- Preserve the documented CLI exit codes: `0` for success, `1` below the requested threshold, and `2` when the coverage input is missing.
- Preserve compatibility with Cobertura reports both with and without `<method>` elements.
- Keep JSON output machine-readable and Markdown output suitable for PR comments.

## Testing and verification

- Add focused regression tests for every behavior change.
- For parser changes, cover malformed or missing attributes, reports without method data, missing source files, and nested/class functions.
- For scorer changes, cover empty inputs, minimum importance, indicator weighting, path matching, and rounding.
- For CLI changes, verify argument defaults, project-directory resolution, output files, and exit codes.
- Before finishing, run `uv run ruff check .`, the relevant tests, `uv run python -m better_cov --help`, and `uv build`.

## Generated files

Do not commit local environments, caches, build artifacts, `coverage.xml`, `.coverage`, or `better_cov.json`; these are ignored by `.gitignore`.

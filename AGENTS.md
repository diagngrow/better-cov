# AGENTS.md

## Project overview

`better-cov` is a Python CLI that computes function-level coverage weighted by source-level import importance. It consumes Cobertura XML only and supports Python (`.py`), JavaScript (`.js`, `.jsx`, `.mjs`, `.cjs`), and TypeScript (`.ts`, `.tsx`, `.mts`, `.cts`). Python analysis uses the standard-library AST; JavaScript and TypeScript analysis uses Tree-sitter. The CLI prints a terminal report and can export JSON or Markdown.

## Environment

- Use Python 3.12 for local development (`.python-version`).
- Keep compatibility with Python 3.10+ as declared in `pyproject.toml`.
- Use `uv` for dependency and command management.
- Install or synchronize the environment with `uv sync`.
- Run project commands through `uv run`.
- Runtime parsing and resolution depend on `json5`, `tree-sitter`, `tree-sitter-javascript`, and `tree-sitter-typescript`; pytest, pytest-cov, and Ruff are declared in the `dev` dependency group.

## Repository layout

- `better_cov/cli.py`: argument parsing, `PROJECT_DIR` path resolution, language selection, and exit codes.
- `better_cov/languages/base.py`: language adapter contracts and shared source-analysis models.
- `better_cov/languages/registry.py`: `auto`/explicit adapter selection by file extension.
- `better_cov/languages/python.py`: Python AST extraction and module resolution.
- `better_cov/languages/javascript.py`: Tree-sitter JavaScript/JSX extraction, imports, exports, and relative resolution.
- `better_cov/languages/typescript.py`: TypeScript/TSX adapter and config-aware resolution.
- `better_cov/languages/typescript_config.py`: JSONC `tsconfig.json`/`jsconfig.json`, `baseUrl`, `paths`, local `extends`, and project-reference resolution.
- `better_cov/parsers/cobertura.py`: Cobertura parsing and adapter-based function extraction.
- `better_cov/indicators/`: importance indicator interface and multi-language import counting.
- `better_cov/models.py`: shared coverage data models.
- `better_cov/scorer.py`: weighted coverage calculation and result models.
- `better_cov/reporter.py`: console, JSON, and Markdown reports.
- `.githooks/pre-commit` and `scripts/pre-commit.sh`: versioned Ruff and test checks.
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

The versioned `.githooks/pre-commit` hook delegates to `scripts/pre-commit.sh`, which runs Ruff and the complete test suite. Enable it once per clone with:

```bash
git config core.hooksPath .githooks
```

Run the checks manually with `./scripts/pre-commit.sh`.

To exercise Python coverage:

```bash
uv run pytest --cov=better_cov --cov-report=xml:coverage.xml
uv run better-cov --coverage-xml coverage.xml --source-dirs better_cov --language python
```

For Jest, generate Cobertura with `coverageReporters: ['text', 'cobertura']`. For Vitest, configure `coverage.reporter` with `['text', 'cobertura']`. In `PROJECT_DIR` mode, the CLI checks `coverage.xml` and then `coverage/cobertura-coverage.xml`, and discovers direct or nested `src/` directories.

## Implementation conventions

- Use `from __future__ import annotations` in Python modules.
- Avoid new dependencies unless the feature clearly requires them; this project is not stdlib-only.
- Use type hints on public and internal function signatures.
- Use `pathlib.Path` for filesystem operations.
- Use dataclasses for structured parser, scoring, resolution, and report data.
- Keep language-specific parsing and resolution behind adapters in `better_cov/languages/`; keep orchestration in the parser and indicator layers.
- Keep CLI concerns in `cli.py`, Cobertura parsing in `parsers/`, importance logic in `indicators/`, scoring in `scorer.py`, and presentation/export in `reporter.py`.
- Keep scores normalized to the `0.0`–`1.0` range internally; convert to percentages only at reporting boundaries.
- Preserve `--language auto|python|javascript|typescript`; `auto` selects adapters from source extensions.
- Preserve the documented CLI exit codes: `0` for success, `1` below the requested threshold, and `2` when the coverage input is missing.
- Preserve Cobertura reports both with and without `<method>` elements, including Istanbul's hits-only method data.
- Keep JSON output machine-readable and Markdown output suitable for PR comments.

## TypeScript resolution boundaries

- Parse JSONC through `json5` and support `compilerOptions.baseUrl`, `compilerOptions.paths`, relative or absolute local `extends`, and project `references` for monorepos.
- Resolve only against scanned source files, including TypeScript counterparts for `.js`, `.jsx`, `.mjs`, and `.cjs` specifiers.
- Do not traverse or resolve `node_modules`.
- Do not treat package-based `extends`, Node package resolution, or aliases defined only by bundlers as supported. Bundler aliases must also be represented by local `baseUrl`/`paths` configuration.

## Testing and verification

- Add focused regression tests for every behavior change.
- `tests/test_javascript.py` covers JS/JSX and TS/TSX functions, ESM/CommonJS imports and exports, type-only syntax, and relative resolution.
- `tests/test_typescript_config.py` covers JSONC, `baseUrl`, exact and wildcard `paths`, local `extends`, monorepo references, extension substitution, invalid configs, and `node_modules` exclusions.
- `tests/test_parser.py` covers Cobertura parsing, source fallbacks, Python ranges, and Jest/Vitest-style JavaScript methods.
- `tests/test_indicator.py` covers Python imports, JavaScript named imports, TypeScript aliases, and ignored type-only imports.
- `tests/test_cli.py` covers argument defaults, `--language`, `PROJECT_DIR` report/source discovery, end-to-end JavaScript, outputs, and exit codes.
- Keep scorer and reporter edge cases in `tests/test_scorer.py` and `tests/test_reporter.py`.
- Before finishing, run `uv run ruff check .`, the relevant tests, `uv run python -m better_cov --help`, and `uv build`.

## Generated files

Do not commit local environments, caches, build artifacts, generated `coverage.xml`/`coverage/` reports, `.coverage`, `better_cov.json`, or generated Markdown reports. Cobertura files under `tests/fixtures/` are committed test data.

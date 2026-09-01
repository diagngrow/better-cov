# better-cov

[![PyPI version](https://badge.fury.io/py/better-cov.svg)](https://pypi.org/project/better-cov/)
[![Python](https://img.shields.io/pypi/pyversions/better-cov.svg)](https://pypi.org/project/better-cov/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**Coverage score weighted by function importance.**

Standard line coverage treats every function equally. `better-cov` gives a higher weight to functions that are actually used — measured by how often they are imported across your codebase — so the score reflects what matters most.

Supported source files are Python (`.py`), JavaScript (`.js`, `.jsx`, `.mjs`, `.cjs`), and TypeScript (`.ts`, `.tsx`, `.mts`, `.cts`).

## How it works

```text
weighted_score = Σ(line_rate_i × importance_i) / Σ(importance_i)
```

1. Parses a Cobertura XML coverage report.
2. Extracts function-level coverage from report methods or source ranges.
3. Uses Python's AST or Tree-sitter for JavaScript and TypeScript source analysis.
4. Counts resolved runtime imports and re-exports across source files.
5. Computes a weighted score, prints it, and exports JSON (and optionally Markdown).

`better-cov` accepts **Cobertura XML only**. LCOV and tool-specific JSON formats are not supported.

## Installation

```bash
# Via pip (recommended)
pip install better-cov

# Via uv
uv add better-cov

# Via pipx (isolated CLI)
pipx install better-cov
```

## Quick start

```bash
# Auto-detect the report, source directories, and languages from a project root
better-cov /path/to/your/project

# Explicit paths and language
better-cov --coverage-xml coverage.xml --source-dirs src/ --language python

# Multiple source directories
better-cov --coverage-xml coverage.xml --source-dirs packages/app/src packages/lib/src
```

With `PROJECT_DIR`, `better-cov` checks `coverage.xml` and then `coverage/cobertura-coverage.xml`. It uses the root `src/` directory when present, otherwise it discovers nested `src/` directories for monorepos.

## Generate Cobertura coverage

### Python / pytest

```bash
pytest --cov=src --cov-report=xml:coverage.xml
```

### JavaScript / TypeScript with Jest

Add Cobertura to `jest.config.js`, `jest.config.ts`, or the equivalent project configuration:

```js
module.exports = {
  collectCoverage: true,
  coverageReporters: ['text', 'cobertura'],
};
```

Jest writes `coverage/cobertura-coverage.xml` by default.

### JavaScript / TypeScript with Vitest

Set `coverage.reporter` in `vitest.config.js` or `vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    coverage: {
      reporter: ['text', 'cobertura'],
    },
  },
});
```

Vitest also writes `coverage/cobertura-coverage.xml` by default.

## CLI reference

```text
usage: better_cov [-h] [--coverage-xml PATH] [--source-dirs DIR [DIR ...]]
                  [--language {auto,python,javascript,typescript}]
                  [--output PATH] [--min-score PCT] [--min-importance FLOAT]
                  [--top-n N] [--markdown-output PATH] [PROJECT_DIR]
```

| Argument | Default | Description |
|---|---|---|
| `PROJECT_DIR` | — | Project root used to auto-detect the Cobertura report and `src/` directories |
| `--coverage-xml` | `coverage.xml` | Path to a Cobertura XML report |
| `--source-dirs` | `src/` | Directories scanned to compute import counts |
| `--language` | `auto` | `auto`, `python`, `javascript`, or `typescript`; auto-detection uses file extensions |
| `--output` | `better_cov.json` | JSON export path |
| `--markdown-output` | — | Optional Markdown export path |
| `--min-score` | — | Fail with exit code 1 if the score is below this percentage |
| `--min-importance` | `0.1` | Floor importance for functions with zero imports |
| `--top-n` | `10` | Number of functions shown in console and Markdown reports |

Language selection maps to these extensions:

| Value | Extensions |
|---|---|
| `python` | `.py` |
| `javascript` | `.js`, `.jsx`, `.mjs`, `.cjs` |
| `typescript` | `.ts`, `.tsx`, `.mts`, `.cts` |
| `auto` | All of the above, selected per file |

## TypeScript module resolution

TypeScript imports are resolved against scanned source files using local `tsconfig.json` and `jsconfig.json` files. The resolver supports:

- JSONC configuration, `compilerOptions.baseUrl`, and `compilerOptions.paths`;
- relative or absolute local `extends` chains;
- project `references`, including referenced packages in monorepos;
- TypeScript equivalents for `.js`, `.jsx`, `.mjs`, and `.cjs` import specifiers.

Resolution deliberately excludes `node_modules`. Package-based `extends`, Node package resolution, and aliases defined only in bundler configuration are not supported; expose local aliases through `baseUrl`/`paths` and include their files in `--source-dirs`.

## CI integration

### GitHub Action

```yaml
- name: Run tests with coverage
  run: pytest --cov=src --cov-report=xml:coverage.xml

- name: Check weighted coverage
  uses: diagngrow/better-cov@main
  with:
    coverage-xml: coverage.xml
    source-dirs: src/
    language: auto
    min-score: 60
```

### Manual install

```yaml
- name: Check weighted coverage
  run: |
    pip install better-cov
    better-cov . --language auto --min-score 60
```

Exit codes: `0` = success, `1` = below threshold, `2` = input file not found.

## Output

The console report shows weighted and raw coverage plus the most important functions. `better_cov.json` contains the aggregate scores, configuration, and per-function coverage and importance; use `--markdown-output` for a PR-friendly report.

## Project structure

```text
better_cov/
├── languages/
│   ├── base.py              # Language adapter contracts
│   ├── registry.py          # --language selection and extension detection
│   ├── python.py            # Python AST analysis and import resolution
│   ├── javascript.py        # Tree-sitter JavaScript/JSX analysis
│   ├── typescript.py        # Tree-sitter TypeScript/TSX adapter
│   └── typescript_config.py # JSONC config and monorepo path resolution
├── parsers/
│   └── cobertura.py         # Cobertura-only coverage parser
├── indicators/
│   ├── base.py              # ImportanceIndicator abstract interface
│   └── import_count.py      # Multi-language import-count indicator
├── models.py                # Shared coverage models
├── scorer.py                # Weighted score computation
├── reporter.py              # Console, JSON, and Markdown reports
└── cli.py                   # CLI entry point
```

## Requirements

- Python ≥ 3.10
- Runtime source analysis uses `json5`, `tree-sitter`, `tree-sitter-javascript`, and `tree-sitter-typescript`

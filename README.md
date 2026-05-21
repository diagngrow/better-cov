# better-cov

[![PyPI version](https://badge.fury.io/py/better-cov.svg)](https://pypi.org/project/better-cov/)
[![Python](https://img.shields.io/pypi/pyversions/better-cov.svg)](https://pypi.org/project/better-cov/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**Coverage score weighted by function importance.**

Standard line coverage treats every function equally. `better-cov` gives a higher weight to functions that are actually used — measured by how often they are imported across your codebase — so the score reflects what matters most.

## How it works

```
weighted_score = Σ(line_rate_i × importance_i) / Σ(importance_i)
```

1. Parses a `coverage.xml` (Cobertura format, produced by `pytest-cov`)
2. Extracts function-level coverage using AST when method-level data is absent
3. Counts how many times each function is imported across source files (`from module import symbol`)
4. Computes a weighted score — heavily-imported functions have more influence on the final score
5. Reports results to console and exports a JSON file

## Installation

```bash
# Via pip (recommandé)
pip install better-cov

# Via uv
uv add better-cov

# Via pipx (CLI isolé)
pipx install better-cov
```

## Quick start

```bash
# Auto-detect coverage.xml and src/ from a project root
better-cov /path/to/your/project

# Explicit paths
better-cov --coverage-xml coverage.xml --source-dirs src/

# Multiple source directories
better-cov --coverage-xml coverage.xml --source-dirs src/ lib/ core/
```

Generate `coverage.xml` with pytest-cov beforehand:

```bash
pytest --cov=src --cov-report=xml
```

## CLI reference

```
usage: better_cov [-h] [--coverage-xml PATH] [--source-dirs DIR [DIR ...]]
                  [--output PATH] [--min-score PCT] [--min-importance FLOAT]
                  [--top-n N] [PROJECT_DIR]
```

| Argument | Default | Description |
|---|---|---|
| `PROJECT_DIR` | — | Project root: auto-detects `coverage.xml` and `src/` subdirectories |
| `--coverage-xml` | `coverage.xml` | Path to the Cobertura XML report |
| `--source-dirs` | `src/` | Directories scanned to compute import counts |
| `--output` | `better_cov.json` | JSON export path |
| `--min-score` | — | Fail with exit code 1 if score is below this threshold (useful in CI) |
| `--min-importance` | `0.1` | Floor importance for functions with zero imports |
| `--top-n` | `10` | Number of functions shown in the console report |

## CI integration

### GitHub Action (recommended)

```yaml
- name: Run tests with coverage
  run: pytest --cov=src --cov-report=xml

- name: Check weighted coverage
  uses: diagngrow/better-cov@main
  with:
    coverage-xml: coverage.xml
    source-dirs: src/
    min-score: 60
```

### Manual install

```yaml
- name: Run tests with coverage
  run: pytest --cov=src --cov-report=xml

- name: Check weighted coverage
  run: |
    pip install better-cov
    better-cov --coverage-xml coverage.xml --source-dirs src/ --min-score 60
```

Exit codes: `0` = success, `1` = below threshold, `2` = input file not found.

## Output

### Console

```
  Weighted Coverage Report
──────────────────────────────────────────────────────────────
  Weighted score    52.0%  [██████████░░░░░░░░░░]
  Raw coverage      43.5%  [█████████░░░░░░░░░░░]
  Difference        +8.5%

  Indicators : import_count
  Functions  : 144

  Top 10 most important functions

  File                                  Function                    Coverage  Importance
  mypackage/helpers.py                  process_response             100.0%     0.500
  mypackage/core.py                     load_model                    95.8%     0.500
  mypackage/helpers.py                  normalize_response           100.0%     0.375
  ...
```

### JSON (`better_cov.json`)

```json
{
  "generated_at": "2026-05-21T15:00:00+00:00",
  "global_score": 0.52,
  "global_score_pct": 52.0,
  "raw_coverage": 0.435,
  "total_functions": 144,
  "indicators": ["import_count"],
  "functions": [
    {
      "file": "mypackage/helpers.py",
      "function": "process_response",
      "line_rate": 1.0,
      "lines_covered": 5,
      "lines_total": 5,
      "importance": 0.5,
      "weighted_contribution": 0.5,
      "indicator_scores": { "import_count": 0.5 }
    }
  ]
}
```

## Project structure

```
better_cov/
├── parsers/
│   └── cobertura.py        # Cobertura XML parser + AST function extraction
├── indicators/
│   ├── base.py             # ImportanceIndicator abstract interface
│   └── import_count.py     # Import-count indicator
├── scorer.py               # Weighted score computation
├── reporter.py             # Console report + JSON export
└── cli.py                  # CLI entry point
```

## Requirements

- Python ≥ 3.12
- No runtime dependencies (stdlib only)

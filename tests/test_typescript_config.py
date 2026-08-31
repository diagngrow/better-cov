from __future__ import annotations

from pathlib import Path

from better_cov.languages.typescript_config import TypeScriptConfigResolver


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_resolves_relative_files_and_directory_indexes(tmp_path: Path) -> None:
    """Relative imports resolve extensionless files and directory index files."""
    importer = _write(tmp_path / "src" / "main.ts")
    utility = _write(tmp_path / "src" / "utility.ts")
    component = _write(tmp_path / "src" / "component" / "index.tsx")
    resolver = TypeScriptConfigResolver()
    sources = [importer, utility, component]

    assert resolver.resolve("./utility", importer, sources, []) == utility
    assert resolver.resolve("./component", importer, sources, []) == component


def test_replaces_javascript_import_extension_with_typescript_source(
    tmp_path: Path,
) -> None:
    """A .js import prefers its corresponding TypeScript source file."""
    importer = _write(tmp_path / "src" / "main.ts")
    typescript_source = _write(tmp_path / "src" / "service.ts")
    javascript_source = _write(tmp_path / "src" / "service.js")

    resolved = TypeScriptConfigResolver().resolve(
        "./service.js",
        importer,
        [importer, javascript_source, typescript_source],
        [],
    )

    assert resolved == typescript_source


def test_reads_jsonc_and_resolves_modules_from_base_url(tmp_path: Path) -> None:
    """JSONC comments and trailing commas are accepted when applying baseUrl."""
    importer = _write(tmp_path / "src" / "main.ts")
    target = _write(tmp_path / "src" / "library" / "tool.ts")
    _write(
        tmp_path / "tsconfig.json",
        """{
  // TypeScript configuration files permit comments.
  "compilerOptions": {
    "baseUrl": "./src",
  },
}
""",
    )

    resolved = TypeScriptConfigResolver().resolve(
        "library/tool", importer, [importer, target], [tmp_path]
    )

    assert resolved == target


def test_paths_use_priority_wildcards_and_multiple_targets(tmp_path: Path) -> None:
    """Path rules prefer exact/specific patterns and try targets in order."""
    importer = _write(tmp_path / "src" / "main.ts")
    fallback = _write(tmp_path / "src" / "fallback" / "ordinary.ts")
    specific = _write(tmp_path / "src" / "special" / "tool.ts")
    specific_trap = _write(tmp_path / "src" / "fallback" / "special" / "tool.ts")
    exact = _write(tmp_path / "src" / "exact.ts")
    exact_trap = _write(tmp_path / "src" / "fallback" / "exact.ts")
    _write(
        tmp_path / "tsconfig.json",
        """{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["missing/*", "src/fallback/*"],
      "@/special/*": ["src/special/*"],
      "@/exact": ["src/exact.ts"]
    }
  }
}
""",
    )
    sources = [
        importer,
        fallback,
        specific,
        specific_trap,
        exact,
        exact_trap,
    ]
    resolver = TypeScriptConfigResolver()

    assert resolver.resolve("@/ordinary", importer, sources, [tmp_path]) == fallback
    assert resolver.resolve("@/special/tool", importer, sources, [tmp_path]) == specific
    assert resolver.resolve("@/exact", importer, sources, [tmp_path]) == exact


def test_resolves_aliases_from_jsconfig(tmp_path: Path) -> None:
    """JavaScript projects can define aliases in jsconfig.json."""
    importer = _write(tmp_path / "app" / "main.js")
    target = _write(tmp_path / "app" / "shared" / "value.js")
    _write(
        tmp_path / "jsconfig.json",
        '{"compilerOptions":{"baseUrl":"app","paths":{"#/*":["shared/*"]}}}',
    )

    resolved = TypeScriptConfigResolver().resolve(
        "#/value", importer, [importer, target], [tmp_path]
    )

    assert resolved == target


def test_local_extends_keeps_path_targets_relative_to_their_origin(
    tmp_path: Path,
) -> None:
    """Inherited relative options remain anchored to the config that defines them."""
    importer = _write(tmp_path / "apps" / "web" / "src" / "main.ts")
    inherited_target = _write(tmp_path / "configs" / "sources" / "tool.ts")
    child_trap = _write(tmp_path / "apps" / "web" / "sources" / "tool.ts")
    _write(
        tmp_path / "configs" / "base.json",
        """{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {"@shared/*": ["sources/*"]}
  }
}
""",
    )
    _write(
        tmp_path / "apps" / "web" / "tsconfig.json",
        """{
  "extends": "../../configs/base",
  "compilerOptions": {"baseUrl": "."}
}
""",
    )

    resolved = TypeScriptConfigResolver().resolve(
        "@shared/tool",
        importer,
        [importer, inherited_target, child_trap],
        [tmp_path],
    )

    assert resolved == inherited_target


def test_cyclic_local_extends_does_not_recurse_forever(tmp_path: Path) -> None:
    """Cycles in local extends chains terminate while retaining usable options."""
    importer = _write(tmp_path / "src" / "main.ts")
    target = _write(tmp_path / "src" / "cycle.ts")
    _write(
        tmp_path / "tsconfig.json",
        '{"extends":"./base.json"}',
    )
    _write(
        tmp_path / "base.json",
        """{
  "extends": "./tsconfig.json",
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {"cycle": ["src/cycle.ts"]}
  }
}
""",
    )

    resolved = TypeScriptConfigResolver().resolve(
        "cycle", importer, [importer, target], [tmp_path]
    )

    assert resolved == target


def test_nearest_config_takes_precedence_over_ancestor_config(tmp_path: Path) -> None:
    """The config closest to the importer wins when aliases overlap."""
    importer = _write(tmp_path / "packages" / "app" / "main.ts")
    root_target = _write(tmp_path / "root.ts")
    nearest_target = _write(tmp_path / "packages" / "app" / "nearest.ts")
    _write(
        tmp_path / "tsconfig.json",
        """{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {"choice": ["root.ts"]}
  }
}
""",
    )
    _write(
        tmp_path / "packages" / "app" / "tsconfig.json",
        """{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {"choice": ["nearest.ts"]}
  }
}
""",
    )

    resolved = TypeScriptConfigResolver().resolve(
        "choice",
        importer,
        [importer, root_target, nearest_target],
        [tmp_path],
    )

    assert resolved == nearest_target


def test_project_references_resolve_across_a_monorepo(tmp_path: Path) -> None:
    """Referenced package configs contribute aliases to sibling workspaces."""
    importer = _write(tmp_path / "packages" / "app" / "src" / "main.ts")
    target = _write(tmp_path / "packages" / "library" / "src" / "tool.ts")
    _write(
        tmp_path / "tsconfig.json",
        """{
  "files": [],
  "references": [
    {"path": "./packages/app"},
    {"path": "./packages/library"}
  ]
}
""",
    )
    _write(tmp_path / "packages" / "app" / "tsconfig.json", "{}")
    _write(
        tmp_path / "packages" / "library" / "tsconfig.json",
        """{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {"@library/*": ["src/*"]}
  }
}
""",
    )

    resolved = TypeScriptConfigResolver().resolve(
        "@library/tool", importer, [importer, target], [tmp_path]
    )

    assert resolved == target


def test_node_modules_sources_and_configs_are_ignored(tmp_path: Path) -> None:
    """Vendored sources, explicit paths, and configs under node_modules are ignored."""
    importer = _write(tmp_path / "src" / "main.ts")
    outside_target = _write(tmp_path / "src" / "outside.ts")
    vendored_target = _write(tmp_path / "node_modules" / "vendor" / "hidden.ts")
    vendored_importer = _write(tmp_path / "node_modules" / "vendor" / "main.ts")
    _write(
        tmp_path / "tsconfig.json",
        """{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {"vendor-only": ["node_modules/vendor/hidden.ts"]}
  }
}
""",
    )
    _write(
        tmp_path / "node_modules" / "vendor" / "tsconfig.json",
        """{
  "compilerOptions": {
    "baseUrl": "../..",
    "paths": {"outside": ["src/outside.ts"]}
  }
}
""",
    )
    sources = [importer, outside_target, vendored_target, vendored_importer]
    resolver = TypeScriptConfigResolver()

    assert resolver.resolve("vendor-only", importer, sources, [tmp_path]) is None
    assert resolver.resolve(
        "outside", vendored_importer, sources, [vendored_importer.parent]
    ) is None
    assert resolver.resolve(
        "./node_modules/vendor/hidden", importer, sources, [tmp_path]
    ) is None


def test_invalid_config_is_ignored_without_breaking_resolution(tmp_path: Path) -> None:
    """Malformed configuration is ignored without raising or blocking relative imports."""
    importer = _write(tmp_path / "src" / "main.ts")
    target = _write(tmp_path / "src" / "valid.ts")
    _write(tmp_path / "tsconfig.json", '{"compilerOptions": {invalid json')
    resolver = TypeScriptConfigResolver()
    sources = [importer, target]

    assert resolver.resolve("./valid", importer, sources, [tmp_path]) == target
    assert resolver.resolve("unknown-alias", importer, sources, [tmp_path]) is None

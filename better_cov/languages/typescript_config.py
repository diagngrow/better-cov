from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import json5

_EXTENSIONS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
_EXTENSION_REPLACEMENTS = {
    ".js": (".ts", ".tsx", ".js", ".jsx"),
    ".jsx": (".tsx", ".jsx"),
    ".mjs": (".mts", ".mjs"),
    ".cjs": (".cts", ".cjs"),
}


@dataclass(frozen=True)
class _PathRule:
    pattern: str
    targets: tuple[str, ...]
    anchor: Path


@dataclass(frozen=True)
class _Config:
    base_url: Path | None = None
    paths: tuple[_PathRule, ...] = ()
    references: tuple[Path, ...] = ()


class TypeScriptConfigResolver:
    def __init__(self) -> None:
        """Initialize the resolver and its parsed-config cache."""
        self._cache: dict[Path, tuple[tuple[int, int], dict[str, object] | None]] = {}

    def resolve(
        self,
        module: str,
        importer: Path,
        source_files: list[Path],
        source_dirs: list[Path],
    ) -> Path | None:
        """Resolve a module specifier against scanned files and local configs."""
        module = module.replace("\\", "/")
        if not module or self._has_node_modules(Path(module)):
            return None
        files: dict[Path, Path] = {}
        for source in source_files:
            normalized = self._normalize(source)
            if not self._has_node_modules(normalized):
                files.setdefault(normalized, source)
        if not files:
            return None
        importer_path = self._normalize(importer)
        if module in {".", ".."} or module.startswith(("./", "../")):
            return self._resolve_path(importer_path.parent / module, files)
        if Path(module).is_absolute():
            return self._resolve_path(Path(module), files)
        for config_path in self._config_paths(importer_path, source_dirs):
            config = self._config(config_path, frozenset())
            matched = self._matching_rule(module, config.paths)
            if matched is not None:
                rule, wildcard = matched
                for target in rule.targets:
                    replacement = target.replace("*", wildcard)
                    resolved = self._resolve_path(rule.anchor / replacement, files)
                    if resolved is not None:
                        return resolved
            if config.base_url is not None:
                resolved = self._resolve_path(config.base_url / module, files)
                if resolved is not None:
                    return resolved
        return None

    def _resolve_path(self, path: Path, files: dict[Path, Path]) -> Path | None:
        """Resolve a path using supported extensions while excluding node_modules."""
        for candidate in self._candidates(path):
            normalized = self._normalize(candidate)
            if self._has_node_modules(normalized):
                continue
            source = files.get(normalized)
            if source is not None:
                return source
        return None

    def _candidates(self, path: Path) -> tuple[Path, ...]:
        """Build extension-substitution, extension, and index candidates."""
        suffix = path.suffix.lower()
        candidates: list[Path] = []
        if suffix in _EXTENSION_REPLACEMENTS:
            stem = path.with_suffix("")
            candidates.extend(
                Path(f"{stem}{extension}")
                for extension in _EXTENSION_REPLACEMENTS[suffix]
            )
        elif suffix in _EXTENSIONS:
            candidates.append(path)
        else:
            candidates.append(path)
            candidates.extend(Path(f"{path}{extension}") for extension in _EXTENSIONS)
            candidates.extend(path / f"index{extension}" for extension in _EXTENSIONS)
        return tuple(dict.fromkeys(candidates))

    def _config_paths(
        self, importer: Path, source_dirs: list[Path]
    ) -> tuple[Path, ...]:
        """Collect local configs, following references and skipping node_modules."""
        paths: list[Path] = []
        seen: set[Path] = set()

        def add(path: Path) -> None:
            """Add a config and its references once, excluding node_modules."""
            normalized = self._normalize(path)
            if normalized in seen or self._has_node_modules(normalized):
                return
            seen.add(normalized)
            if not normalized.is_file():
                return
            paths.append(normalized)
            config = self._config(normalized, frozenset())
            for reference in config.references:
                add(reference)

        nearest = self._nearest_config(importer.parent)
        if nearest is not None:
            add(nearest)
        for ancestor in self._ancestors(importer.parent):
            config = self._config_in(ancestor)
            if config is not None:
                add(config)
        for source_dir in source_dirs:
            directory = self._normalize(source_dir)
            if directory.is_file():
                directory = directory.parent
            nearest = self._nearest_config(directory)
            if nearest is not None:
                add(nearest)
            if not directory.is_dir() or self._has_node_modules(directory):
                continue
            for root, directories, names in os.walk(directory):
                directories[:] = sorted(
                    name for name in directories if name.lower() != "node_modules"
                )
                root_path = Path(root)
                if "tsconfig.json" in names:
                    add(root_path / "tsconfig.json")
                elif "jsconfig.json" in names:
                    add(root_path / "jsconfig.json")
        return tuple(paths)

    def _nearest_config(self, directory: Path) -> Path | None:
        """Find the nearest tsconfig.json or jsconfig.json ancestor."""
        for ancestor in self._ancestors(directory):
            config = self._config_in(ancestor)
            if config is not None:
                return config
        return None

    def _ancestors(self, directory: Path) -> tuple[Path, ...]:
        """Return normalized ancestors until a node_modules path is reached."""
        current = self._normalize(directory)
        result: list[Path] = []
        while not self._has_node_modules(current):
            result.append(current)
            if current.parent == current:
                break
            current = current.parent
        return tuple(result)

    @staticmethod
    def _config_in(directory: Path) -> Path | None:
        """Find a TypeScript or JavaScript config directly in a directory."""
        for name in ("tsconfig.json", "jsconfig.json"):
            candidate = directory / name
            if candidate.is_file():
                return candidate
        return None

    def _config(self, path: Path, seen: frozenset[Path]) -> _Config:
        """Load JSON5 config options, local extends, and project references."""
        path = self._normalize(path)
        if path in seen or self._has_node_modules(path):
            return _Config()
        raw = self._read(path)
        if raw is None:
            return _Config()
        chain = seen | {path}
        merged = _Config()
        extends = raw.get("extends")
        values = [extends] if isinstance(extends, str) else extends
        if isinstance(values, list):
            for value in values:
                if not isinstance(value, str):
                    continue
                parent_path = self._local_config_path(value, path.parent)
                if parent_path is not None:
                    parent = self._config(parent_path, chain)
                    merged = _Config(parent.base_url, parent.paths, merged.references)
        options = raw.get("compilerOptions")
        if isinstance(options, dict):
            typed_options = cast(dict[str, object], options)
            base_url = merged.base_url
            local_base_url = typed_options.get("baseUrl")
            if isinstance(local_base_url, str):
                base_url = self._normalize(path.parent / local_base_url)
            rules = merged.paths
            raw_paths = typed_options.get("paths")
            if isinstance(raw_paths, dict):
                anchor = base_url or path.parent
                rules = self._path_rules(cast(dict[object, object], raw_paths), anchor)
            merged = _Config(base_url, rules, merged.references)
        references = self._references(raw.get("references"), path.parent)
        return _Config(merged.base_url, merged.paths, references)

    def _read(self, path: Path) -> dict[str, object] | None:
        """Read and cache a JSON5 object using its file-stat signature."""
        try:
            stat = path.stat()
        except OSError:
            return None
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(path)
        if cached is not None and cached[0] == signature:
            return cached[1]
        try:
            value = json5.loads(path.read_text(encoding="utf-8"))
            result = cast(dict[str, object], value) if isinstance(value, dict) else None
        except (OSError, UnicodeError, ValueError, TypeError):
            result = None
        self._cache[path] = (signature, result)
        return result

    def _local_config_path(self, value: str, origin: Path) -> Path | None:
        """Resolve a relative or absolute local extends target."""
        raw = Path(value)
        if not raw.is_absolute() and not value.startswith(("./", "../", ".\\", "..\\")):
            return None
        base = raw if raw.is_absolute() else origin / raw
        return self._find_config_target(base)

    def _find_config_target(self, base: Path) -> Path | None:
        """Find a config file, JSON variant, or config directory target."""
        candidates = [base]
        if base.suffix.lower() != ".json":
            candidates.append(Path(f"{base}.json"))
        candidates.extend((base / "tsconfig.json", base / "jsconfig.json"))
        for candidate in candidates:
            normalized = self._normalize(candidate)
            if not self._has_node_modules(normalized) and normalized.is_file():
                return normalized
        return None

    def _references(self, value: object, origin: Path) -> tuple[Path, ...]:
        """Resolve local project-reference paths to existing config files."""
        if not isinstance(value, list):
            return ()
        references: list[Path] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            target = item.get("path")
            if not isinstance(target, str):
                continue
            raw = Path(target)
            base = raw if raw.is_absolute() else origin / raw
            config = self._find_config_target(base)
            if config is not None:
                references.append(config)
        return tuple(dict.fromkeys(references))

    @staticmethod
    def _path_rules(value: dict[object, object], anchor: Path) -> tuple[_PathRule, ...]:
        """Build validated compilerOptions.paths rules anchored at a base URL."""
        rules: list[_PathRule] = []
        for pattern, raw_targets in value.items():
            if not isinstance(pattern, str) or pattern.count("*") > 1:
                continue
            if not isinstance(raw_targets, list):
                continue
            targets = tuple(
                target
                for target in raw_targets
                if isinstance(target, str) and target.count("*") <= 1
            )
            if targets:
                rules.append(_PathRule(pattern, targets, anchor))
        return tuple(rules)

    @staticmethod
    def _matching_rule(
        module: str, rules: tuple[_PathRule, ...]
    ) -> tuple[_PathRule, str] | None:
        """Select the most specific exact or wildcard paths rule."""
        matches: list[tuple[tuple[int, int, int], int, _PathRule, str]] = []
        for order, rule in enumerate(rules):
            if "*" not in rule.pattern:
                if module == rule.pattern:
                    matches.append(
                        ((1, len(rule.pattern), len(rule.pattern)), order, rule, "")
                    )
                continue
            prefix, suffix = rule.pattern.split("*", 1)
            if (
                module.startswith(prefix)
                and module.endswith(suffix)
                and len(module) >= len(prefix) + len(suffix)
            ):
                wildcard = module[
                    len(prefix) : len(module) - len(suffix) if suffix else None
                ]
                matches.append(
                    ((0, len(prefix) + len(suffix), len(prefix)), order, rule, wildcard)
                )
        if not matches:
            return None
        _, _, rule, wildcard = min(
            matches,
            key=lambda item: (-item[0][0], -item[0][1], -item[0][2], item[1]),
        )
        return rule, wildcard

    @staticmethod
    def _normalize(path: Path) -> Path:
        """Normalize a path without requiring it to exist."""
        return path.expanduser().resolve(strict=False)

    @staticmethod
    def _has_node_modules(path: Path) -> bool:
        """Return whether a path contains a node_modules component."""
        return any(part.lower() == "node_modules" for part in path.parts)

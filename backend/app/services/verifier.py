"""Deterministic checks for facts that should not be left to the LLM."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class VerificationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ImportRef:
    file_path: str
    line: int
    module: str
    statement: str


@dataclass(frozen=True)
class ImportedSymbolRef:
    file_path: str
    line: int
    module: str
    symbol: str
    import_kind: str
    statement: str


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    detail: str


@dataclass(frozen=True)
class DependencyIndex:
    packages: dict[str, str]
    package_json_found: bool


@dataclass(frozen=True)
class AliasRule:
    prefix: str
    suffix: str
    targets: tuple[str, ...]


@dataclass(frozen=True)
class PathAliasIndex:
    base_url: str
    rules: tuple[AliasRule, ...]
    config_found: bool


_IMPORT_RE = re.compile(
    r"^\s*import\s+(?:type\s+)?(?:.+?\s+from\s+)?[\"']([^\"']+)[\"']\s*;?\s*$"
)
_REQUIRE_RE = re.compile(r"^\s*(?:const|let|var)\s+.+?=\s*require\([\"']([^\"']+)[\"']\)\s*;?\s*$")
_DYNAMIC_IMPORT_RE = re.compile(r"\bimport\([\"']([^\"']+)[\"']\)")
_NAMED_IMPORT_RE = re.compile(r"^\s*import\s+(?:type\s+)?\{(.+)}\s+from\s+[\"']([^\"']+)[\"']\s*;?\s*$")
_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_RELATIVE_PREFIXES = ("./", "../")
_RESOLVE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)
_ALIAS_CONFIG_FILES = ("tsconfig.json", "jsconfig.json")


def extract_imports_from_diff(diff: str) -> list[ImportRef]:
    imports: list[ImportRef] = []
    current_file: str | None = None
    new_line: int | None = None

    for raw_line in diff.splitlines():
        header = _DIFF_HEADER_RE.match(raw_line)
        if header:
            current_file = header.group(2)
            new_line = None
            continue

        hunk = _HUNK_RE.match(raw_line)
        if hunk:
            new_line = int(hunk.group(1))
            continue

        if new_line is None:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):  # added code line
            code = raw_line[1:]
            module = _extract_module(code)
            if module and current_file:
                imports.append(
                    ImportRef(
                        file_path=current_file,
                        line=new_line,
                        module=module,
                        statement=code.strip(),
                    )
                )
            new_line += 1
            continue

        if raw_line.startswith("-") and not raw_line.startswith("---"):
            continue

        new_line += 1

    return imports


def extract_imported_symbols_from_diff(diff: str) -> list[ImportedSymbolRef]:
    symbols: list[ImportedSymbolRef] = []
    current_file: str | None = None
    new_line: int | None = None

    for raw_line in diff.splitlines():
        header = _DIFF_HEADER_RE.match(raw_line)
        if header:
            current_file = header.group(2)
            new_line = None
            continue

        hunk = _HUNK_RE.match(raw_line)
        if hunk:
            new_line = int(hunk.group(1))
            continue

        if new_line is None:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            code = raw_line[1:].strip()
            named_import = _NAMED_IMPORT_RE.match(code)
            if named_import and current_file:
                module = named_import.group(2)
                if _is_relative_import(module) or _looks_like_path_alias(module):
                    for symbol in _extract_named_imports(named_import.group(1)):
                        symbols.append(
                            ImportedSymbolRef(
                                file_path=current_file,
                                line=new_line,
                                module=module,
                                symbol=symbol,
                                import_kind="named",
                                statement=code,
                            )
                        )
            new_line += 1
            continue

        if raw_line.startswith("-") and not raw_line.startswith("---"):
            continue

        new_line += 1

    return symbols


def build_dependency_index(repo_path: Path) -> DependencyIndex:
    package_json = repo_path / "package.json"
    if not package_json.exists():
        return DependencyIndex(packages={}, package_json_found=False)

    try:
        data = json.loads(package_json.read_text())
    except (OSError, json.JSONDecodeError):
        return DependencyIndex(packages={}, package_json_found=True)

    packages: dict[str, str] = {}
    for section in _DEPENDENCY_SECTIONS:
        values = data.get(section, {})
        if not isinstance(values, dict):
            continue
        for name in values:
            packages[name] = section

    return DependencyIndex(packages=packages, package_json_found=True)


def build_path_alias_index(repo_path: Path) -> PathAliasIndex:
    for config_name in _ALIAS_CONFIG_FILES:
        config_path = repo_path / config_name
        if not config_path.exists():
            continue
        try:
            data = json.loads(config_path.read_text())
        except (OSError, json.JSONDecodeError):
            return PathAliasIndex(base_url=".", rules=(), config_found=True)

        compiler_options = data.get("compilerOptions", {})
        if not isinstance(compiler_options, dict):
            return PathAliasIndex(base_url=".", rules=(), config_found=True)

        base_url = compiler_options.get("baseUrl", ".")
        if not isinstance(base_url, str):
            base_url = "."

        rules = []
        paths = compiler_options.get("paths", {})
        if isinstance(paths, dict):
            for pattern, targets in paths.items():
                if not isinstance(pattern, str) or not isinstance(targets, list):
                    continue
                parsed = _parse_alias_pattern(pattern)
                if parsed is None:
                    continue
                valid_targets = tuple(target for target in targets if isinstance(target, str))
                if valid_targets:
                    rules.append(AliasRule(parsed[0], parsed[1], valid_targets))

        return PathAliasIndex(base_url=base_url, rules=tuple(rules), config_found=True)

    return PathAliasIndex(base_url=".", rules=(), config_found=False)


def import_exists(repo_path: Path, import_ref: ImportRef) -> VerificationResult:
    if _is_relative_import(import_ref.module):
        return _relative_import_exists(repo_path, import_ref)
    if _looks_like_path_alias(import_ref.module):
        return _path_alias_import_exists(repo_path, import_ref.file_path, import_ref.module)

    return package_dependency_exists(repo_path, import_ref.module)


def verify_imported_symbol(repo_path: Path, symbol_ref: ImportedSymbolRef) -> VerificationResult:
    if not _is_relative_import(symbol_ref.module) and not _looks_like_path_alias(symbol_ref.module):
        return VerificationResult(VerificationStatus.UNKNOWN, "package named exports are not verified")

    target = _resolve_import_path(repo_path, symbol_ref.file_path, symbol_ref.module)
    if target.status != VerificationStatus.PASS:
        return target

    target_file = repo_path.resolve() / target.detail
    exports, has_export_star = _collect_js_ts_exports(target_file)
    if symbol_ref.symbol in exports:
        return VerificationResult(VerificationStatus.PASS, "named export found")
    if has_export_star:
        return VerificationResult(VerificationStatus.UNKNOWN, "export * re-export requires recursive resolution")
    return VerificationResult(VerificationStatus.FAIL, f"{symbol_ref.symbol} is not exported by {target.detail}")


def package_dependency_exists(
    repo_path: Path,
    package: str,
    dependency_index: DependencyIndex | None = None,
) -> VerificationResult:
    index = dependency_index or build_dependency_index(repo_path)
    if not index.package_json_found:
        return VerificationResult(VerificationStatus.UNKNOWN, "package.json not found")

    package_name = _package_name(package)
    section = index.packages.get(package_name)
    if section:
        return VerificationResult(VerificationStatus.PASS, section)

    return VerificationResult(VerificationStatus.FAIL, f"{package_name} not declared in package.json")


def verify_diff_imports(repo_path: Path, diff: str) -> dict:
    imports = extract_imports_from_diff(diff)
    symbols = extract_imported_symbols_from_diff(diff)
    dependency_index = build_dependency_index(repo_path)
    results = []

    for import_ref in imports:
        if _is_relative_import(import_ref.module):
            verification = _relative_import_exists(repo_path, import_ref)
        elif _looks_like_path_alias(import_ref.module):
            verification = _path_alias_import_exists(
                repo_path,
                import_ref.file_path,
                import_ref.module,
            )
        else:
            verification = package_dependency_exists(repo_path, import_ref.module, dependency_index)
        results.append(
            {
                "file": import_ref.file_path,
                "line": import_ref.line,
                "module": import_ref.module,
                "statement": import_ref.statement,
                "status": verification.status.value,
                "detail": verification.detail,
            }
        )

    export_results = []
    for symbol_ref in symbols:
        verification = verify_imported_symbol(repo_path, symbol_ref)
        target_detail = ""
        if verification.status == VerificationStatus.PASS:
            target = _resolve_import_path(repo_path, symbol_ref.file_path, symbol_ref.module)
            target_detail = target.detail if target.status == VerificationStatus.PASS else ""
        export_results.append(
            {
                "file": symbol_ref.file_path,
                "line": symbol_ref.line,
                "module": symbol_ref.module,
                "symbol": symbol_ref.symbol,
                "import_kind": symbol_ref.import_kind,
                "statement": symbol_ref.statement,
                "target_file": target_detail,
                "status": verification.status.value,
                "detail": verification.detail,
            }
        )

    return {"imports": results, "exports": export_results}


def _extract_module(code: str) -> str | None:
    for pattern in (_IMPORT_RE, _REQUIRE_RE, _DYNAMIC_IMPORT_RE):
        match = pattern.search(code)
        if match:
            return match.group(1)
    return None


def _relative_import_exists(repo_path: Path, import_ref: ImportRef) -> VerificationResult:
    return _resolve_relative_import(repo_path, import_ref.file_path, import_ref.module)


def _path_alias_import_exists(repo_path: Path, file_path: str, module: str) -> VerificationResult:
    return _resolve_path_alias_import(repo_path, file_path, module)


def _resolve_import_path(repo_path: Path, file_path: str, module: str) -> VerificationResult:
    if _is_relative_import(module):
        return _resolve_relative_import(repo_path, file_path, module)
    if _looks_like_path_alias(module):
        return _resolve_path_alias_import(repo_path, file_path, module)
    return VerificationResult(VerificationStatus.UNKNOWN, "package import path is not resolved")


def _resolve_relative_import(repo_path: Path, file_path: str, module: str) -> VerificationResult:
    importer = repo_path / file_path
    target_base = (importer.parent / module).resolve()
    repo_root = repo_path.resolve()

    try:
        target_base.relative_to(repo_root)
    except ValueError:
        return VerificationResult(VerificationStatus.UNKNOWN, "relative import resolves outside repository")

    for candidate in _relative_candidates(target_base):
        if candidate.is_file():
            return VerificationResult(VerificationStatus.PASS, str(candidate.relative_to(repo_root)))

    return VerificationResult(VerificationStatus.FAIL, f"{module} not found from {file_path}")


def _resolve_path_alias_import(repo_path: Path, file_path: str, module: str) -> VerificationResult:
    alias_index = build_path_alias_index(repo_path)
    if not alias_index.config_found or not alias_index.rules:
        return VerificationResult(VerificationStatus.UNKNOWN, f"path alias for {module} is not configured")

    repo_root = repo_path.resolve()
    base_dir = (repo_root / alias_index.base_url).resolve()
    try:
        base_dir.relative_to(repo_root)
    except ValueError:
        return VerificationResult(VerificationStatus.UNKNOWN, "path alias baseUrl resolves outside repository")

    for rule in alias_index.rules:
        matched = _match_alias_rule(module, rule)
        if matched is None:
            continue
        for target_pattern in rule.targets:
            target_path = _apply_alias_target(base_dir, target_pattern, matched)
            try:
                target_path.relative_to(repo_root)
            except ValueError:
                continue
            for candidate in _relative_candidates(target_path):
                if candidate.is_file():
                    return VerificationResult(VerificationStatus.PASS, str(candidate.relative_to(repo_root)))

    return VerificationResult(VerificationStatus.FAIL, f"{module} not found from {file_path}")


def _relative_candidates(target_base: Path) -> list[Path]:
    candidates = [target_base]
    candidates.extend(Path(f"{target_base}{ext}") for ext in _RESOLVE_EXTENSIONS)
    candidates.extend(target_base / f"index{ext}" for ext in _RESOLVE_EXTENSIONS)
    return candidates


def _is_relative_import(module: str) -> bool:
    return module.startswith(_RELATIVE_PREFIXES)


def _looks_like_path_alias(module: str) -> bool:
    return module.startswith("@/") or module.startswith("~/") or module.startswith("#/")


def _package_name(module: str) -> str:
    parts = module.split("/")
    if module.startswith("@") and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def _extract_named_imports(import_block: str) -> list[str]:
    symbols = []
    for part in import_block.split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        symbol = re.split(r"\s+as\s+", cleaned, maxsplit=1)[0].strip()
        if symbol and symbol != "type":
            symbols.append(symbol.removeprefix("type ").strip())
    return [symbol for symbol in symbols if symbol]


def _collect_js_ts_exports(path: Path) -> tuple[set[str], bool]:
    try:
        source = path.read_text()
    except OSError:
        return set(), False
    return _extract_named_exports(source)


def _extract_named_exports(source: str) -> tuple[set[str], bool]:
    exports: set[str] = set()
    has_export_star = False

    if re.search(r"^\s*export\s+\*\s+from\s+[\"']", source, re.MULTILINE):
        has_export_star = True

    declaration_re = re.compile(
        r"^\s*export\s+(?:declare\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+)",
        re.MULTILINE,
    )
    exports.update(match.group(1) for match in declaration_re.finditer(source))

    for match in re.finditer(r"^\s*export\s+\{([^}]+)}", source, re.MULTILINE):
        for part in match.group(1).split(","):
            exported = _exported_name_from_part(part)
            if exported:
                exports.add(exported)

    return exports, has_export_star


def _exported_name_from_part(part: str) -> str | None:
    cleaned = part.strip()
    if not cleaned:
        return None
    pieces = re.split(r"\s+as\s+", cleaned, maxsplit=1)
    if len(pieces) == 2:
        return pieces[1].strip()
    return pieces[0].strip()


def _parse_alias_pattern(pattern: str) -> tuple[str, str] | None:
    if pattern.count("*") > 1:
        return None
    if "*" not in pattern:
        return pattern, ""
    prefix, suffix = pattern.split("*", 1)
    return prefix, suffix


def _match_alias_rule(module: str, rule: AliasRule) -> str | None:
    if not module.startswith(rule.prefix) or not module.endswith(rule.suffix):
        return None
    return module[len(rule.prefix): len(module) - len(rule.suffix) if rule.suffix else len(module)]


def _apply_alias_target(base_dir: Path, target_pattern: str, matched: str) -> Path:
    target = target_pattern.replace("*", matched)
    return (base_dir / target).resolve()

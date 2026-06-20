"""Unified SAST wrapper using Semgrep.

Runs Semgrep on specified files and returns findings in FindingSchema format.
Silently degrades if Semgrep is unavailable or files don't exist.
"""

import asyncio
import json
import logging
import re
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_SECURITY_RULES = ["p/security-audit", "p/owasp-top-ten"]
_QUALITY_RULES = ["p/python", "p/javascript", "p/typescript"]


async def run_sast(
    files: list[str],
    rule_type: str,
    base_path: Path | None = None,
    diff: str | None = None,
) -> list[dict]:
    if not files:
        return []

    rules = _SECURITY_RULES if rule_type == "security" else _QUALITY_RULES

    target_paths = []
    for f in files:
        p = Path(f)
        if not p.is_absolute() and base_path:
            p = base_path / p
        if p.exists():
            target_paths.append(str(p))

    if not target_paths:
        return []

    try:
        result = await _run_semgrep(target_paths, rules)
        return _parse_results(result, base_path=base_path, diff=diff, category=rule_type)
    except Exception as e:
        logger.debug("semgrep scan failed (%s): %s", rule_type, e)
        return []


async def _run_semgrep(target_paths: list[str], rules: list[str]) -> dict:
    semgrep_path = shutil.which("semgrep") or _find_semgrep()
    if not semgrep_path:
        logger.debug("semgrep not found")
        return {}

    config_args = []
    for rule in rules:
        config_args.extend(["--config", rule])

    proc = await asyncio.create_subprocess_exec(
        semgrep_path, "scan",
        *config_args,
        "--json",
        "--no-rewrite-rule-ids",
        "--quiet",
        "--skip-unknown-extensions",
        *target_paths,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

    if proc.returncode not in (0, 1):
        logger.debug("semgrep exited %d: %s", proc.returncode, stderr.decode()[:200])
        return {}

    return json.loads(stdout.decode())


_SEVERITY_MAP = {
    "ERROR": "ERROR",
    "WARNING": "WARNING",
    "INFO": "INFO",
}


def _find_semgrep() -> str | None:
    venv_bin = Path(sys.prefix) / "bin" / "semgrep"
    if venv_bin.exists():
        return str(venv_bin)
    return None


def _parse_results(
    data: dict,
    base_path: Path | None = None,
    diff: str | None = None,
    category: str = "security",
) -> list[dict]:
    if not data:
        return []

    added_lines = _extract_added_lines(diff or "") if diff is not None else None
    findings = []
    seen: set[tuple[str, int, int, str]] = set()

    for r in data.get("results", []):
        extra = r.get("extra", {})
        check_id = r.get("check_id", "")
        path = _normalize_path(r.get("path", ""), base_path)
        if path is None:
            continue

        start_line = r.get("start", {}).get("line", 0)
        end_line = r.get("end", {}).get("line", start_line)
        if not isinstance(start_line, int) or start_line <= 0:
            continue
        if not isinstance(end_line, int) or end_line < start_line:
            end_line = start_line

        line = start_line
        evidence = [extra.get("message", "")]
        if added_lines is not None:
            intersecting = [
                added_line for added_line in sorted(added_lines.get(path, {}))
                if start_line <= added_line <= end_line
            ]
            if not intersecting:
                continue
            line = intersecting[0]
            evidence = [added_lines[path][line]]

        key = (path, start_line, end_line, check_id)
        if key in seen:
            continue
        seen.add(key)

        severity = _SEVERITY_MAP.get(extra.get("severity", "WARNING"), "WARNING")
        message = extra.get("message", "")

        findings.append({
            "file": path,
            "line": line,
            "title": check_id.split(".")[-1],
            "description": message,
            "severity": severity,
            "confidence": 0.95,
            "category": category,
            "impact_type": "security_risk" if category == "security" else "runtime_error",
            "impact_statement": message,
            "evidence": evidence,
            "source": "sast",
        })

    return findings


def _normalize_path(path: str, base_path: Path | None = None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if base_path is None:
        return p.as_posix()
    if not p.is_absolute():
        return p.as_posix()

    try:
        return p.resolve().relative_to(base_path.resolve()).as_posix()
    except ValueError:
        return None


def _extract_added_lines(diff: str) -> dict[str, dict[int, str]]:
    added: dict[str, dict[int, str]] = {}
    current_file: str | None = None
    new_line: int | None = None

    for raw_line in diff.splitlines():
        line = raw_line.lstrip()

        if line.startswith("diff --git"):
            current_file = _parse_diff_git_path(line)
            if current_file is not None:
                added.setdefault(current_file, {})
            new_line = None
            continue
        if line.startswith("+++ b/"):
            current_file = line[6:]
            added.setdefault(current_file, {})
            continue
        if line.startswith("@@"):
            new_line = _parse_new_hunk_start(line)
            continue
        if current_file is None or new_line is None:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            added[current_file][new_line] = line
            new_line += 1
            continue
        if line.startswith("-") and not line.startswith("---"):
            continue
        new_line += 1

    return {file: lines for file, lines in added.items() if lines}


def _parse_new_hunk_start(line: str) -> int | None:
    match = re.search(r"\+(\d+)(?:,\d+)?", line)
    if not match:
        return None
    return int(match.group(1))


def _parse_diff_git_path(line: str) -> str | None:
    parts = line.split()
    if len(parts) < 4:
        return None
    new_path = parts[3]
    if not new_path.startswith("b/"):
        return None
    return new_path[2:]

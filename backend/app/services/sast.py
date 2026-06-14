"""Unified SAST wrapper using Semgrep.

Runs Semgrep on specified files and returns findings in FindingSchema format.
Silently degrades if Semgrep is unavailable or files don't exist.
"""

import asyncio
import json
import logging
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
        return _parse_results(result)
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


def _parse_results(data: dict) -> list[dict]:
    if not data:
        return []

    findings = []
    seen: set[str] = set()

    for r in data.get("results", []):
        extra = r.get("extra", {})
        check_id = r.get("check_id", "")

        if check_id in seen:
            continue
        seen.add(check_id)

        path = r.get("path", "")
        line = r.get("start", {}).get("line", 0)
        severity = _SEVERITY_MAP.get(extra.get("severity", "WARNING"), "WARNING")
        message = extra.get("message", "")

        findings.append({
            "file": path,
            "line": line,
            "title": check_id.split(".")[-1],
            "description": message,
            "severity": severity,
            "confidence": 0.95,
            "category": "security",
            "evidence": [message],
            "source": "sast",
        })

    return findings

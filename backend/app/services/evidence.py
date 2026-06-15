from app.models.agent import FindingSchema
from app.services.diff import build_position_map

SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}


def added_lines_by_file(diff: str) -> dict[str, list[str]]:
    lines_by_file: dict[str, list[str]] = {}
    current_file: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            lines_by_file.setdefault(current_file, [])
        elif current_file is not None and line.startswith("+") and not line.startswith("+++"):
            lines_by_file[current_file].append(line[1:])
    return lines_by_file


def added_diff_lines(diff: str) -> list[str]:
    by_file = added_lines_by_file(diff)
    if by_file:
        return [line for lines in by_file.values() for line in lines]
    return [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def severity(finding: FindingSchema) -> str:
    return finding.severity if isinstance(finding.severity, str) else finding.severity.value


def evidence_matches_added_line(finding: FindingSchema, diff: str) -> bool:
    file_lines = added_lines_by_file(diff).get(finding.file, [])
    if not file_lines:
        return False
    return any(
        evidence in line
        for evidence in finding.evidence or []
        for line in file_lines
    )


def finding_targets_added_line(finding: FindingSchema, diff: str) -> bool:
    if finding.line is None:
        return True
    return finding.line in build_position_map(diff).get(finding.file, {})


def publication_gate(findings: list[FindingSchema], diff: str) -> list[FindingSchema]:
    kept: dict[tuple[str, int | None, str], FindingSchema] = {}
    for finding in findings:
        if severity(finding) == "INFO":
            continue
        if not finding.evidence:
            continue
        if not finding_targets_added_line(finding, diff):
            continue
        if not evidence_matches_added_line(finding, diff):
            continue

        key = (finding.file, finding.line, finding.title)
        existing = kept.get(key)
        if existing is None or _finding_rank(finding) < _finding_rank(existing):
            kept[key] = finding
    return list(kept.values())


def _finding_rank(finding: FindingSchema) -> tuple[int, float]:
    return (SEVERITY_ORDER.get(severity(finding), 99), -finding.confidence)

import re

from app.models.agent import FindingSchema
from app.services.diff import build_position_map

SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}

# ---------------------------------------------------------------------------
# Non-executable context detection (single-line comments only)
# ---------------------------------------------------------------------------
# Industry practice: deterministic single-line check only.
# Multiline docstring tracking via diff reconstruction is fragile (context
# lines may be absent from diff, breaking state machines). Instead, LLM
# agents are instructed in their system prompts not to report issues inside
# docstrings or comments — that handles the multiline case at the source.

def _is_comment_line(stripped: str) -> bool:
    if stripped.startswith(("# ", "#!", "//")):
        return True
    # "* " or lone "*" = JSDoc comment line; "**kwargs" or "*args" are not
    if stripped.startswith("* ") or stripped == "*":
        return True
    if stripped.startswith("/*"):
        return True
    return False


def is_line_in_non_executable_context(diff: str, file_path: str, line_num: int) -> bool:
    """Return True if the reported line is a single-line comment.

    Only checks for lines starting with # (Python) or // (JS/TS) or
    * / /* (JSDoc). Multiline docstring detection is intentionally removed:
    it required fragile diff reconstruction that caused false drops of real
    findings. LLM agents are prompted to skip docstring content directly.
    """
    if line_num is None:
        return False

    # Reconstruct just the target line from diff (+ and context lines).
    current_file: str | None = None
    in_target = False
    new_line = 0
    for raw in diff.split("\n"):
        if raw.startswith("+++ b/"):
            current_file = raw[6:]
            in_target = (current_file == file_path)
            new_line = 0
        elif raw.startswith("@@") and in_target:
            m = re.search(r"\+(\d+)", raw)
            if m:
                new_line = int(m.group(1)) - 1
        elif in_target:
            if raw.startswith("+") and not raw.startswith("+++"):
                new_line += 1
                if new_line == line_num:
                    stripped = raw[1:].strip()
                    return _is_comment_line(stripped)
            elif raw.startswith(" "):
                new_line += 1
                if new_line == line_num:
                    stripped = raw[1:].strip()
                    return _is_comment_line(stripped)
    return False


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
        evidence.lstrip("+") in line
        for evidence in finding.evidence or []
        for line in file_lines
    )


def _all_lines_by_file(diff: str) -> dict[str, set[int]]:
    """返回 diff 中每个文件实际出现过的行号（新文件行号，包含 context 和新增行）。"""
    result: dict[str, set[int]] = {}
    current_file: str | None = None
    new_line = 0
    import re
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            current_file = line[6:]
            new_line = 0
            result[current_file] = set()
        elif line.startswith("@@") and current_file is not None:
            m = re.search(r"\+(\d+)", line)
            if m:
                new_line = int(m.group(1)) - 1
        elif current_file is not None:
            if line.startswith("+") and not line.startswith("+++"):
                new_line += 1
                result[current_file].add(new_line)
            elif line.startswith("-"):
                pass  # 删除行不增加新文件行号
            elif line.startswith(" "):
                new_line += 1
                result[current_file].add(new_line)
    return result


def finding_targets_added_line(finding: FindingSchema, diff: str) -> bool:
    """验证 finding 的行号在 diff 对应文件里真实存在（新增行或 context 行均可）。
    行号为 None 时放行，防止模型对完全不在 diff 里的文件报问题。
    删除类 bug 的行号通常落在 context 行上，也应放行。"""
    if finding.line is None:
        return True
    # 先检查 position map（新增行）
    if finding.line in build_position_map(diff).get(finding.file, {}):
        return True
    # 再检查是否在 diff 任意可见行（context 行）
    return finding.line in _all_lines_by_file(diff).get(finding.file, set())


def publication_gate(findings: list[FindingSchema], diff: str) -> list[FindingSchema]:
    import logging
    _log = logging.getLogger(__name__)

    kept: dict[tuple[str, int | None, str], FindingSchema] = {}
    for finding in findings:
        if severity(finding) == "INFO":
            continue
        # CONTEXT 来源引用 blast radius 跨文件代码，不在 diff 里，
        # 跳过行号门控但要求 evidence 非空，防止纯幻觉
        if finding.evidence_source == "CONTEXT":
            if not finding.evidence:
                continue
        else:
            if not finding_targets_added_line(finding, diff):
                continue
            # 过滤掉落在注释 / docstring / 字符串字面量内的 finding，
            # 防止 LLM 把文档示例代码当真实代码报 false positive
            if finding.line is not None and is_line_in_non_executable_context(
                diff, finding.file, finding.line
            ):
                _log.info(
                    "evidence gate: dropped finding in non-executable context "
                    "[%s:%s] %s",
                    finding.file, finding.line, finding.title,
                )
                continue

        key = (finding.file, finding.line, finding.title)
        existing = kept.get(key)
        if existing is None or _finding_rank(finding) < _finding_rank(existing):
            kept[key] = finding
    return list(kept.values())


def _finding_rank(finding: FindingSchema) -> tuple[int, float]:
    return (SEVERITY_ORDER.get(severity(finding), 99), -finding.confidence)

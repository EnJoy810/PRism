import re

from app.models.agent import FindingSchema
from app.services.diff import build_position_map

SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}

# ---------------------------------------------------------------------------
# Non-executable context detection (comment / docstring / string literal)
# ---------------------------------------------------------------------------

def _reconstruct_file_lines(diff: str, file_path: str) -> dict[int, str]:
    """从 diff 重建指定文件的行号→内容映射（新增行 + context 行，不含删除行）。"""
    result: dict[int, str] = {}
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
                result[new_line] = raw[1:]
            elif raw.startswith(" "):
                new_line += 1
                result[new_line] = raw[1:]
    return result


def is_line_in_non_executable_context(diff: str, file_path: str, line_num: int) -> bool:
    """检查 diff 中某行是否落在注释或多行字符串（docstring）内。

    支持：
    - Python triple-quote docstring (''' 或 \"\"\")
    - Python 单行注释 (#)
    - TypeScript/JavaScript 块注释 (/* ... */)
    - TypeScript/JavaScript 单行注释 (//)
    - TypeScript/JavaScript JSDoc (/** ... */)

    实现策略：从目标行之前的所有 diff 行中维护一个简单状态机，
    判断多行注释/docstring 是否已打开但尚未关闭。
    """
    if line_num is None:
        return False

    lines = _reconstruct_file_lines(diff, file_path)
    if not lines:
        return False

    content_at_line = lines.get(line_num, "")
    stripped = content_at_line.strip()

    # 单行注释快速判断
    if (
        stripped.startswith("#")
        or stripped.startswith("//")
        or stripped.startswith("*")   # JSDoc 内容行 (* @param, * text)
        or stripped.startswith("/*")  # 块注释开始行（/* 或 /**）
    ):
        return True

    # 扫描目标行之前的行，维护多行上下文状态
    in_multiline = False
    multiline_closer: str | None = None

    for ln in sorted(ln for ln in lines if ln < line_num):
        line_content = lines[ln]

        if not in_multiline:
            # 检测 Python triple-quote 开启（按长度降序，防止 '' 干扰 '''）
            for marker in ('"""', "'''"):
                count = line_content.count(marker)
                if count % 2 == 1:  # 奇数 = 本行开启但未关闭
                    in_multiline = True
                    multiline_closer = marker
                    break
            # 检测 JS/TS 块注释开启
            if not in_multiline and "/*" in line_content:
                after_open = line_content[line_content.index("/*") + 2:]
                if "*/" not in after_open:
                    in_multiline = True
                    multiline_closer = "*/"
        else:
            assert multiline_closer is not None
            if multiline_closer in line_content:
                in_multiline = False
                multiline_closer = None

    return in_multiline


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

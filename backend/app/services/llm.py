import json
import os
import re
from openai import AsyncOpenAI
from app.models.review import ReviewIssue, ReviewResult, Severity

MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com/v1"

SYSTEM_PROMPT = """你是一位资深软件工程师，正在做代码审查。找出真正的缺陷，而不是风格问题。
用中文回答。

严重级别：
- ERROR: 逻辑错误、安全漏洞、空指针风险、数据丢失风险
- WARNING: 性能问题、非惯用写法、缺少错误处理
- INFO: 微小改进、文档建议（仅当显式请求时）

规则：
1. 只报告你高度确信的问题（>85% 信心）
2. 每个问题锚定到具体文件和行号
3. 提供可操作的建议，而不是模糊的建议
4. 如果 diff 看起来正确，直接说没问题
 5. 除非 options.include_style 为 true，否则不报 INFO"""

SECURITY_PROMPT = """你是一位专注于安全审计的资深工程师，正在做代码审查。用中文回答。

严重级别：
- ERROR: SQL 注入、XSS、CSRF、敏感信息泄露、认证授权缺陷、命令注入
- WARNING: 输入验证不足、HTTPS 缺失、权限控制不严、不安全随机数
- INFO: 安全最佳实践建议（仅当显式请求时）

规则：
1. 只关注安全相关的问题，忽略风格和性能
2. 每个问题提供具体的攻击场景和修复方法
3. 如果未发现安全问题，直接说：本次变更未发现安全风险"""

PERFORMANCE_PROMPT = """你是一位专注于性能优化的资深工程师，正在做代码审查。用中文回答。

严重级别：
- ERROR: N+1 查询、内存泄漏、死锁、大对象重复创建、同步阻塞 IO
- WARNING: 不必要的循环、缓存缺失、懒加载缺失、批量操作可优化
- INFO: 微小性能改进建议（仅当显式请求时）

规则：
1. 只关注性能相关的问题，忽略安全和风格
2. 提供数据量级估算（如：1000 次请求时，这个循环会…）
3. 如果未发现性能问题，直接说：本次变更未发现性能风险"""

MAINTAINABILITY_PROMPT = """你是一位关注代码可维护性的资深工程师，正在做代码审查。用中文回答。

严重级别：
- ERROR: 明显的设计缺陷、职责边界混乱、状态管理不一致
- WARNING: 重复代码、过长函数、命名混乱、缺少类型约束、过度耦合
- INFO: 代码组织建议、TS 类型优化、注释位置（仅当显式请求时）

规则：
1. 只关注可维护性和代码质量，忽略安全和性能
2. 每次指出问题给出重构方向（如：建议抽离为独立函数）
3. 如果代码质量良好，直接说：本次变更代码质量良好"""

PERSPECTIVE_MAP = {
    "default": SYSTEM_PROMPT,
    "security": SECURITY_PROMPT,
    "performance": PERFORMANCE_PROMPT,
    "maintainability": MAINTAINABILITY_PROMPT,
}

REVIEW_PROMPT_TEMPLATE = """PR 标题: {title}
PR 描述: {description}
基准分支: {base_branch} → {head_branch}

变更文件: {files}

Diff:
{diff}

分析这个 PR，返回以下 JSON 结构（字段名用英文，内容用中文）：
{{
  "summary": "2-3 句总结 PR 做了什么及整体质量",
  "risk_level": "HIGH|MEDIUM|LOW",
  "issues": [
    {{
      "severity": "ERROR|WARNING|INFO",
      "file": "path/to/file.ts",
      "line": 42,
      "title": "简短问题标题",
      "description": "问题详细说明",
      "suggestion": "具体修复建议"
    }}
  ]
}}

只返回有效 JSON，不要 markdown 代码块标记。"""


def _make_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=BASE_URL)


def _extract_json(text: str) -> str:
    text = text.strip()
    fence_m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if fence_m:
        return fence_m.group(1).strip()
    return text


def _get_system_prompt(perspective: str = "default") -> str:
    return PERSPECTIVE_MAP.get(perspective, SYSTEM_PROMPT)


def _build_prompt(pr_context: dict) -> str:
    return REVIEW_PROMPT_TEMPLATE.format(
        title=pr_context["title"],
        description=pr_context["description"][:500],
        base_branch=pr_context["base_branch"],
        head_branch=pr_context["head_branch"],
        files=", ".join(pr_context["files"][:20]),
        diff=pr_context["diff"][:80000],
    )


async def analyze_pr(pr_context: dict, include_style: bool = False, perspective: str = "default") -> ReviewResult:
    client = _make_client()
    prompt = _build_prompt(pr_context)

    response = await client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        temperature=1.0,
        top_p=1.0,
        messages=[
            {"role": "system", "content": _get_system_prompt(perspective)},
            {"role": "user", "content": prompt},
        ],
    )

    raw = _extract_json(response.choices[0].message.content or "{}")
    data = json.loads(raw)

    issues = [ReviewIssue(**issue) for issue in data.get("issues", [])]

    if not include_style:
        issues = [i for i in issues if i.severity != Severity.INFO]

    stats = pr_context["stats"]
    stats.issues_by_severity = {
        "ERROR": sum(1 for i in issues if i.severity == Severity.ERROR),
        "WARNING": sum(1 for i in issues if i.severity == Severity.WARNING),
        "INFO": sum(1 for i in issues if i.severity == Severity.INFO),
    }

    return ReviewResult(
        pr_url=pr_context.get("pr_url", ""),
        summary=data.get("summary", ""),
        risk_level=data.get("risk_level", "LOW"),
        issues=issues,
        stats=stats,
    )


CURSOR_PATH_SYSTEM_PROMPT = """You are analyzing a code diff for a reviewer.
List the line numbers (1-indexed) that contain actual code changes.
Focus on +/- lines. Prioritize logic changes over imports/boilerplate.
Return a JSON array of integers, e.g. [5, 23, 8, 41]."""


def _fallback_cursor_path(diff_lines: list[str]) -> list[int]:
    add_del: list[int] = []
    other: list[int] = []
    for i, l in enumerate(diff_lines):
        stripped = l.lstrip()
        if stripped.startswith('--- ') or stripped.startswith('+++ ') or stripped.startswith('@@'):
            other.append(i + 1)
        elif l.startswith('+') or l.startswith('-'):
            add_del.append(i + 1)
        else:
            other.append(i + 1)
    return (add_del + other)[:15]


async def generate_cursor_path(diff_lines: list[str]) -> list[int]:
    client = _make_client()
    numbered = "\n".join(f"{i+1}: {line}" for i, line in enumerate(diff_lines))
    prompt = f"Diff lines:\n{numbered}\n\nReturn only a JSON array of the most interesting line numbers in reading order."

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            max_tokens=150,
            temperature=0.3,
            messages=[
                {"role": "system", "content": CURSOR_PATH_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        raw = _extract_json(response.choices[0].message.content or "[]")
        path = json.loads(raw)
        if isinstance(path, list) and len(path) > 0 and all(isinstance(i, int) for i in path):
            valid = [i for i in path if 1 <= i <= len(diff_lines)]
            if valid:
                return valid[:15]
    except Exception:
        pass

    return _fallback_cursor_path(diff_lines)


async def stream_analyze_pr(pr_context: dict, perspective: str = "default"):
    client = _make_client()
    prompt = _build_prompt(pr_context)

    stream = await client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        temperature=1.0,
        top_p=1.0,
        stream=True,
        messages=[
            {"role": "system", "content": _get_system_prompt(perspective)},
            {"role": "user", "content": prompt},
        ],
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta

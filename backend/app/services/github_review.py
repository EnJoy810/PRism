import asyncio
import logging

import httpx

from app.models.review import ReviewIssue, ReviewResult

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0


def _format_inline_body(issue: ReviewIssue) -> str:
    severity = issue.severity.value if hasattr(issue.severity, "value") else issue.severity
    lines = [f"**[{severity}] {issue.title}**", "", issue.description]
    suggestion = getattr(issue, "suggestion", None)
    if suggestion:
        lines.append(f"\n💡 **建议**: {suggestion}")
    return "\n".join(lines)


def _build_review_body(
    result: ReviewResult,
    fallback_issues: list[ReviewIssue],
) -> str:
    lines = [
        "## PRism Review",
        "",
        f"**风险等级**: {result.risk_level}",
        "",
        f"**总结**: {result.summary}",
        "",
    ]

    # walkthrough 表（兼容尚未有该字段的旧模型）
    walkthrough = getattr(result, "walkthrough", None) or []
    if walkthrough:
        lines += [
            "## 文件变更速览",
            "| 文件 | 变更说明 |",
            "|------|----------|",
        ]
        for entry in walkthrough:
            # WalkthroughEntry 可能是 dict 或 dataclass/pydantic
            if isinstance(entry, dict):
                path = entry.get("file", "")
                summary = entry.get("summary", "")
            else:
                path = getattr(entry, "file", "")
                summary = getattr(entry, "summary", "")
            lines.append(f"| `{path}` | {summary} |")
        lines.append("")

    # fallback 问题汇总（无法定位到具体行的问题）
    if fallback_issues:
        lines += [
            "## 未定位问题",
            "| 严重程度 | 文件 | 问题 |",
            "|----------|------|------|",
        ]
        for issue in fallback_issues:
            severity = issue.severity.value if hasattr(issue.severity, "value") else issue.severity
            lines.append(f"| {severity} | `{issue.file}` | {issue.title} |")
        lines.append("")

    return "\n".join(lines)


async def post_review_to_github(
    owner: str,
    repo: str,
    pr_number: int,
    github_token: str,
    result: ReviewResult,
    position_map: dict[str, dict[int, int]],
) -> dict:
    inline_comments: list[dict] = []
    fallback_issues: list[ReviewIssue] = []

    for issue in result.issues:
        file_path = getattr(issue, "file", None)
        line_num = getattr(issue, "line", None)

        # 优先尝试从 issue 自身携带的 position 字段（另一 agent 添加）
        position = getattr(issue, "position", None)

        # 如果 issue 没有 position，则从 diff 解析结果中查找
        if position is None and file_path and line_num is not None:
            position = position_map.get(file_path, {}).get(line_num)

        if position is not None and file_path:
            inline_comments.append(
                {
                    "path": file_path,
                    "position": position,
                    "body": _format_inline_body(issue),
                }
            )
        else:
            fallback_issues.append(issue)

    body = _build_review_body(result, fallback_issues)

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                    headers={
                        "Authorization": f"token {github_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    json={
                        "body": body,
                        "event": "COMMENT",
                        "comments": inline_comments,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "html_url": data.get("html_url", ""),
                    "inline_count": len(inline_comments),
                }
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "GitHub API attempt %d failed: %s — retrying in %.1fs",
                    attempt + 1, exc, delay,
                )
                await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]

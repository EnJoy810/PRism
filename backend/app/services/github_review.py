import asyncio
import logging

import httpx

from app.models.review import ReviewIssue, ReviewResult

_BOT_SIGNATURE = "## PRism Review"
_CHECK_NAME = "PRism Review"

logger = logging.getLogger(__name__)

_SEVERITY_LABEL: dict[str, str] = {
    "ERROR": "**[blocking]** 🔴",
    "WARNING": "**[non-blocking]** 🟡",
    "INFO": "**[nitpick]** ℹ️",
}


def _severity_label(severity: str) -> str:
    return _SEVERITY_LABEL.get(severity.upper(), f"**[{severity}]**")


async def create_check_run(
    owner: str,
    repo: str,
    head_sha: str,
    github_token: str,
) -> int | None:
    """Create an in_progress check run. Returns check_run_id or None on failure."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"https://api.github.com/repos/{owner}/{repo}/check-runs",
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "name": _CHECK_NAME,
                    "head_sha": head_sha,
                    "status": "in_progress",
                    "output": {
                        "title": "Reviewing...",
                        "summary": "PRism is analyzing your changes.",
                    },
                },
            )
            resp.raise_for_status()
            check_id = resp.json().get("id")
            logger.info("Created check run %s for %s/%s@%s", check_id, owner, repo, head_sha[:8])
            return check_id
        except Exception as e:
            logger.warning("Failed to create check run: %s", e)
            return None


async def update_check_run(
    owner: str,
    repo: str,
    check_run_id: int,
    github_token: str,
    conclusion: str,
    issue_count: int,
    risk_level: str,
) -> None:
    """Update check run to completed with conclusion."""
    if conclusion == "action_required":
        title = f"Found {issue_count} issue{'s' if issue_count != 1 else ''} · Risk: {risk_level}"
    else:
        title = "No issues found"

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.patch(
                f"https://api.github.com/repos/{owner}/{repo}/check-runs/{check_run_id}",
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "status": "completed",
                    "conclusion": conclusion,
                    "output": {
                        "title": title,
                        "summary": f"PRism review complete. Risk level: **{risk_level}**. {issue_count} issue(s) found.",
                    },
                },
            )
            resp.raise_for_status()
            logger.info("Updated check run %s: %s", check_run_id, conclusion)
        except Exception as e:
            logger.warning("Failed to update check run %s: %s", check_run_id, e)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0


def _format_inline_body(issue: ReviewIssue) -> str:
    severity = issue.severity.value if hasattr(issue.severity, "value") else issue.severity
    label = _severity_label(severity)
    lines = [f"{label} **{issue.title}**", "", issue.description]
    if issue.impact_type:
        lines.append(f"\n影响类型: `{issue.impact_type}`")
    if issue.impact_statement:
        lines.append(f"\n具体后果: {issue.impact_statement}")
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

    if result.diff_truncated:
        lines += [
            "> ⚠️ diff 超过 100KB，仅分析了前 100KB 的变更，部分文件未覆盖。",
            "",
        ]

    # fallback 问题汇总（无法定位到具体行的问题）
    if fallback_issues:
        lines += [
            "## 未定位问题",
            "| 严重程度 | 文件 | 问题 |",
            "|----------|------|------|",
        ]
        for issue in fallback_issues:
            severity = issue.severity.value if hasattr(issue.severity, "value") else issue.severity
            label = _severity_label(severity)
            lines.append(f"| {label} | `{issue.file}` | {issue.title} |")
        lines.append("")

    return "\n".join(lines)


async def dismiss_old_reviews(
    owner: str,
    repo: str,
    pr_number: int,
    github_token: str,
) -> None:
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=headers,
        )
        resp.raise_for_status()
        for review in resp.json():
            if not review.get("body", "").startswith(_BOT_SIGNATURE):
                continue
            try:
                await client.put(
                    f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews/{review['id']}/dismissals",
                    headers=headers,
                    json={"message": "Superseded by updated review"},
                )
                logger.info("Dismissed old review %s for %s/%s#%d", review["id"], owner, repo, pr_number)
            except httpx.HTTPStatusError as e:
                logger.warning("Failed to dismiss review %s: %s", review["id"], e)


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

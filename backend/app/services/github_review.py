import httpx
from app.models.review import ReviewResult


def _get_comment_body(result: ReviewResult) -> str:
    lines = [f"## PRism AI Review ({result.risk_level} Risk)"]
    lines.append("")
    lines.append(result.summary)
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for sev in ["ERROR", "WARNING", "INFO"]:
        count = result.stats.issues_by_severity.get(sev, 0)
        if count > 0:
            lines.append(f"| {sev} | {count} |")
    lines.append("")

    for issue in result.issues:
        emoji = {"ERROR": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(issue.severity.value, "⚪")
        lines.append(f"### {emoji} {issue.title}")
        lines.append(f"- **File**: `{issue.file}`" + (f" (line {issue.line})" if issue.line else ""))
        lines.append(f"- **Severity**: {issue.severity.value}")
        lines.append(f"- **Description**: {issue.description}")
        if issue.suggestion:
            lines.append(f"- **Suggestion**: {issue.suggestion}")
        lines.append("")

    return "\n".join(lines)


async def post_review_to_github(
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
    result: ReviewResult,
) -> dict:
    body = _get_comment_body(result)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={
                "body": body,
                "event": "COMMENT",
                "comments": [],
            },
        )
        resp.raise_for_status()
        return resp.json()

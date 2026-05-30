import base64
import os
import re
import httpx
from app.models.review import ReviewStats


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Parse GitHub PR URL into (owner, repo, pr_number)."""
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.search(pattern, pr_url)
    if not match:
        raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
    return match.group(1), match.group(2), int(match.group(3))


async def _fetch_file_content(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    path: str,
    ref: str,
    headers: dict,
) -> str | None:
    """获取单个文件内容，限制 200 行，失败时返回 None"""
    try:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        lines = content.split("\n")[:200]
        return "\n".join(lines)
    except Exception:
        return None


async def fetch_pr_context(
    owner: str, repo: str, pr_number: int, token: str | None = None
) -> dict:
    """Fetch PR diff, metadata, and related file context from GitHub."""
    effective_token = token or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if effective_token:
        headers["Authorization"] = f"Bearer {effective_token}"

    async with httpx.AsyncClient() as client:
        # Fetch PR metadata
        pr_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=headers,
        )
        pr_resp.raise_for_status()
        pr_data = pr_resp.json()

        # Fetch PR diff
        diff_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
        diff_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=diff_headers,
        )
        diff_resp.raise_for_status()

        # Fetch changed files for stats
        files_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files",
            headers=headers,
        )
        files_resp.raise_for_status()
        files_data = files_resp.json()

        # 取变更最多的前 3 个文件并获取其内容
        top_files = sorted(files_data, key=lambda f: f.get("additions", 0), reverse=True)[:3]
        top_file_names = [f["filename"] for f in top_files]
        head_sha = pr_data["head"]["sha"]
        file_contents: dict[str, str] = {}
        for fname in top_file_names:
            content = await _fetch_file_content(client, owner, repo, fname, head_sha, headers)
            if content:
                file_contents[fname] = content

    stats = ReviewStats(
        files_changed=pr_data["changed_files"],
        additions=pr_data["additions"],
        deletions=pr_data["deletions"],
        issues_by_severity={"ERROR": 0, "WARNING": 0, "INFO": 0},
    )

    return {
        "title": pr_data["title"],
        "description": pr_data.get("body") or "",
        "diff": diff_resp.text,
        "files": [f["filename"] for f in files_data],
        "stats": stats,
        "base_branch": pr_data["base"]["ref"],
        "head_branch": pr_data["head"]["ref"],
        "file_contents": file_contents,
    }

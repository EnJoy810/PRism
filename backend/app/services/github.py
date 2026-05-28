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


async def fetch_pr_context(
    owner: str, repo: str, pr_number: int, token: str | None = None
) -> dict:
    """Fetch PR diff, metadata, and related file context from GitHub."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

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
    }

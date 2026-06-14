import os
import re

import httpx

from app.models.review import ReviewStats


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    pattern = r"github\.com/([^/]+)/([^/]+)/pulls?/(\d+)"
    match = re.search(pattern, pr_url)
    if not match:
        raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
    return match.group(1), match.group(2), int(match.group(3))


async def fetch_pr_context(
    owner: str, repo: str, pr_number: int, token: str | None = None
) -> dict:
    effective_token = token or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if effective_token:
        headers["Authorization"] = f"Bearer {effective_token}"

    async with httpx.AsyncClient() as client:
        pr_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=headers,
        )
        pr_resp.raise_for_status()
        pr_data = pr_resp.json()

        diff_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={**headers, "Accept": "application/vnd.github.v3.diff"},
        )
        diff_resp.raise_for_status()
        diff_text = diff_resp.text
        diff_truncated = False
        if len(diff_text) > 100_000:
            diff_text = diff_text[:100_000]
            diff_truncated = True

        # Paginate through all files
        files_data: list[dict] = []
        page = 1
        while True:
            files_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files",
                headers=headers,
                params={"per_page": 100, "page": page},
            )
            files_resp.raise_for_status()
            page_data = files_resp.json()
            if not page_data:
                break
            files_data.extend(page_data)
            page += 1

    stats = ReviewStats(
        files_changed=pr_data["changed_files"],
        additions=pr_data["additions"],
        deletions=pr_data["deletions"],
        issues_by_severity={"ERROR": 0, "WARNING": 0, "INFO": 0},
    )

    return {
        "title": pr_data["title"],
        "description": pr_data.get("body") or "",
        "diff": diff_text,
        "diff_truncated": diff_truncated,
        "files": [f["filename"] for f in files_data],
        "stats": stats,
        "base_branch": pr_data["base"]["ref"],
        "head_branch": pr_data["head"]["ref"],
        "author_name": pr_data["user"]["login"],
        "author_avatar": pr_data["user"]["avatar_url"],
        "updated_at": pr_data["updated_at"],
        "created_at": pr_data.get("created_at", ""),
        "commits": pr_data.get("commits", 0),
        "files_detail": [
            {"filename": f["filename"], "additions": f["additions"], "deletions": f["deletions"]}
            for f in files_data
        ],
    }

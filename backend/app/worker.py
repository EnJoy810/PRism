"""ARQ background worker for consuming review_queue."""

import logging

import httpx

from app.auth import get_installation_token
from app.config import load_config
from app.graph import ReviewGraph
from app.services.github import parse_pr_url

logger = logging.getLogger(__name__)


async def startup(ctx):
    import redis.asyncio as aioredis
    cfg = load_config()
    ctx["config"] = cfg
    ctx["redis"] = aioredis.from_url(cfg.redis_url, decode_responses=True)


async def shutdown(ctx):
    redis = ctx.get("redis")
    if redis:
        await redis.aclose()


async def _resolve_token(config, installation_id: int | None) -> str | None:
    if installation_id:
        try:
            token = await get_installation_token(installation_id)
            logger.info("Using installation token for installation %d", installation_id)
            return token
        except Exception as e:
            logger.warning(
                "Failed to get installation token for %s: %s — falling back to config token",
                installation_id, e,
            )
    token = config.github_token
    if token:
        return token
    return None


async def _post_access_denied_comment(pr_url: str, token: str) -> None:
    owner, repo, pr_number = parse_pr_url(pr_url)
    body = (
        "## PRism Review\n\n"
        "PRism 无法访问此仓库的代码。可能原因：\n\n"
        "1. PRism App 未安装到此仓库\n"
        "2. 仓库为私有且未被授权\n"
        "3. Token 无此仓库的读取权限\n\n"
        "请确认 [PRism App](https://github.com/apps/prism) 已安装并授权到此仓库。"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={"body": body},
        )
        if resp.status_code == 201:
            logger.info("Posted access-denied notice for %s", pr_url)
        else:
            logger.warning("Failed to post access-denied notice for %s: %s", pr_url, resp.status_code)


async def review_job(ctx, pr_url: str, event: str, installation_id: int | None = None):
    from app.services.github_review import create_check_run, update_check_run

    config = ctx["config"]
    logger.info("Processing review: %s (event=%s)", pr_url, event)

    token = await _resolve_token(config, installation_id)
    if not token:
        logger.warning(
            "No token available for %s — review result available in logs only", pr_url
        )

    # Create in_progress check run immediately so user sees feedback
    check_run_id: int | None = None
    owner, repo, pr_number = parse_pr_url(pr_url)
    head_sha = ""
    if token:
        try:
            # Fetch head SHA for the check run and idempotency lock
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
                    headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
                )
                if resp.status_code == 200:
                    head_sha = resp.json().get("head", {}).get("sha", "")
                    if head_sha:
                        check_run_id = await create_check_run(owner, repo, head_sha, token)
        except Exception as e:
            logger.warning("Failed to create check run: %s", e)

    # Idempotency lock: skip if another job is already reviewing this exact commit.
    # Uses Redis SET NX with a 20-minute TTL so a crashed job doesn't block forever.
    redis = ctx.get("redis")
    if redis and head_sha:
        lock_key = f"prism:review_lock:{owner}/{repo}/{head_sha}"
        acquired = await redis.set(lock_key, "1", nx=True, ex=1200)
        if not acquired:
            logger.info(
                "Skipping duplicate review for %s/%s@%s (lock held)", owner, repo, head_sha[:8]
            )
            return

    try:
        graph = ReviewGraph()
        result = await graph.run(pr_url=pr_url, github_token=token, event=event)

        issue_count = len(result.get("issues", []))
        risk_level = result.get("risk_level", "LOW")
        conclusion = "action_required" if issue_count > 0 else "success"

        if token:
            try:
                await graph.post_comment(result, pr_url, token)
                logger.info("Review comment posted for %s", pr_url)
            except Exception as e:
                logger.error("Failed to post review comment for %s: %s", pr_url, e)

            if check_run_id:
                await update_check_run(owner, repo, check_run_id, token, conclusion, issue_count, risk_level)
        else:
            logger.info("No token — review result available in logs only")

        logger.info(
            "Review complete: %s — %d issues, risk=%s, decision=%s",
            pr_url,
            issue_count,
            risk_level,
            result.get("merge_recommendation", "N/A"),
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (403, 404):
            logger.error("No access to %s: %s", pr_url, e)
            if token:
                await _post_access_denied_comment(pr_url, token)
        else:
            logger.error("Review failed for %s: %s", pr_url, e)
        if token and check_run_id:
            await update_check_run(owner, repo, check_run_id, token, "failure", 0, "N/A")
    except Exception as e:
        logger.error("Review failed for %s: %s", pr_url, e)
        if token and check_run_id:
            await update_check_run(owner, repo, check_run_id, token, "failure", 0, "N/A")


class WorkerSettings:
    functions = [review_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = None
    max_tries = 3
    job_timeout = 900  # 15 minutes

    @classmethod
    def from_url(cls, redis_url: str):
        from arq.connections import RedisSettings
        cls.redis_settings = RedisSettings.from_dsn(redis_url)
        return cls


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config()
    settings = WorkerSettings.from_url(cfg.redis_url)
    from arq import run_worker
    run_worker(settings)


if __name__ == "__main__":
    main()

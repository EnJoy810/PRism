import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import load_config
from app.services.queue import ReviewJob, enqueue_review
from app.services.rate_limit import is_rate_limited

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_PR_ACTIONS = {"opened", "synchronize"}
BOT_TRIGGER = "@prism-bot"


def verify_hmac_signature(
    body: bytes, signature_header: str | None, secret: str
) -> bool:
    if not signature_header or not secret:
        return False
    expected_prefix = "sha256="
    if not signature_header.startswith(expected_prefix):
        return False
    sig = signature_header[len(expected_prefix) :]
    expected_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected_sig)


@router.post("/webhook")
async def handle_webhook(request: Request):
    config = load_config()
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if config.github_webhook_secret:
        if not verify_hmac_signature(body, signature, config.github_webhook_secret):
            return JSONResponse(
                status_code=401, content={"error": "Invalid signature"}
            )

    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    if delivery_id:
        dedup_key = f"prism:webhook:delivery:{delivery_id}"
        redis = request.app.state.redis
        if await redis.exists(dedup_key):
            logger.info("Duplicate delivery ignored: %s", delivery_id)
            return JSONResponse(status_code=200, content={"status": "duplicate"})
        await redis.setex(dedup_key, 3600, "1")

    payload = json.loads(body)
    event = request.headers.get("X-GitHub-Event", "unknown")

    if event == "pull_request":
        action = payload.get("action", "")
        if action not in SUPPORTED_PR_ACTIONS:
            logger.info("Ignoring unsupported PR action: %s", action)
            return JSONResponse(status_code=200, content={"status": "ignored"})

        pull_request = payload.get("pull_request", {})
        job = ReviewJob(
            pr_url=pull_request.get("html_url", ""),
            event=f"pull_request.{action}",
            installation_id=payload.get("installation", {}).get("id"),
        )

    elif event == "issue_comment":
        action = payload.get("action", "")
        if action != "created":
            return JSONResponse(status_code=200, content={"status": "ignored"})

        comment_body = payload.get("comment", {}).get("body", "")
        if BOT_TRIGGER not in comment_body:
            return JSONResponse(status_code=200, content={"status": "ignored"})

        issue = payload.get("issue", {})
        pr_url = issue.get("pull_request", {}).get("html_url", "")
        if not pr_url:
            return JSONResponse(status_code=200, content={"status": "ignored"})
        job = ReviewJob(
            pr_url=pr_url,
            event="issue_comment.created",
            installation_id=payload.get("installation", {}).get("id"),
        )

    else:
        logger.info("Ignoring unsupported event: %s", event)
        return JSONResponse(status_code=200, content={"status": "ignored"})

    if not job.pr_url:
        return JSONResponse(
            status_code=400, content={"error": "No pull_request URL in payload"}
        )

    if await is_rate_limited(request.app.state.redis, job.installation_id):
        logger.warning("Rate limit exceeded for installation %s", job.installation_id)
        return JSONResponse(status_code=429, content={"error": "rate limit exceeded"})

    await enqueue_review(job, request.app.state.redis)
    return JSONResponse(status_code=202, content={"status": "accepted"})

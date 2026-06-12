import hashlib
import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import load_config
from app.services.queue import ReviewJob, enqueue_review

router = APIRouter()


def verify_hmac_signature(
    body: bytes, signature_header: str | None, secret: str
) -> bool:
    if not signature_header or not secret:
        return False
    expected_prefix = "sha256="
    if not signature_header.startswith(expected_prefix):
        return False
    sig = signature_header[len(expected_prefix):]
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

    import json

    payload = json.loads(body)
    event = request.headers.get("X-GitHub-Event", "unknown")
    pull_request = payload.get("pull_request", {})

    job = ReviewJob(
        pr_url=pull_request.get("html_url", ""),
        event=event,
        installation_id=payload.get("installation", {}).get("id"),
    )

    if not job.pr_url:
        return JSONResponse(
            status_code=400, content={"error": "No pull_request URL in payload"}
        )

    await enqueue_review(job, config.redis_url)
    return JSONResponse(status_code=202, content={"status": "accepted"})

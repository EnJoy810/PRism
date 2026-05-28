from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import json

from app.models.review import ReviewRequest
from app.services.github import fetch_pr_context, parse_pr_url
from app.services.llm import analyze_pr

router = APIRouter()


@router.post("/review")
async def create_review(request: ReviewRequest):
    try:
        owner, repo, pr_number = parse_pr_url(request.pr_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        pr_context = await fetch_pr_context(owner, repo, pr_number, request.github_token)
        pr_context["pr_url"] = request.pr_url
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {str(e)}")

    include_style = (request.options or {}).get("include_style", False)

    try:
        result = await analyze_pr(pr_context, include_style=include_style)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM analysis error: {str(e)}")

    return {"code": "0", "message": "ok", "data": result.model_dump()}


@router.post("/review/stream")
async def create_review_stream(request: ReviewRequest):
    """SSE streaming endpoint for real-time review output."""
    try:
        owner, repo, pr_number = parse_pr_url(request.pr_url)
        pr_context = await fetch_pr_context(owner, repo, pr_number, request.github_token)
        pr_context["pr_url"] = request.pr_url
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {str(e)}")

    import anthropic
    from app.services.llm import SYSTEM_PROMPT, REVIEW_PROMPT_TEMPLATE

    async def event_stream():
        client = anthropic.AsyncAnthropic()
        prompt = REVIEW_PROMPT_TEMPLATE.format(
            title=pr_context["title"],
            description=pr_context["description"][:500],
            base_branch=pr_context["base_branch"],
            head_branch=pr_context["head_branch"],
            files=", ".join(pr_context["files"][:20]),
            diff=pr_context["diff"][:80000],
        )
        async with client.messages.stream(
            model="claude-opus-4-5",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'delta': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

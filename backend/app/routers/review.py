from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import json

from app.models.review import ReviewRequest
from app.services.github import fetch_pr_context, parse_pr_url
from app.services.llm import analyze_pr, generate_cursor_path, stream_analyze_pr

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
    try:
        owner, repo, pr_number = parse_pr_url(request.pr_url)
        pr_context = await fetch_pr_context(owner, repo, pr_number, request.github_token)
        pr_context["pr_url"] = request.pr_url
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {str(e)}")

    async def event_stream():
        diff_lines = pr_context["diff"].split("\n")[:80]
        yield f"data: {json.dumps({'type': 'diff', 'lines': diff_lines, 'title': pr_context['title']})}\n\n"

        try:
            path = await generate_cursor_path(diff_lines)
        except Exception:
            path = list(range(1, min(len(diff_lines) + 1, 16)))
        yield f"data: {json.dumps({'type': 'cursor_path', 'cursor_path': path})}\n\n"

        async for delta in stream_analyze_pr(pr_context):
            yield f"data: {json.dumps({'delta': delta})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

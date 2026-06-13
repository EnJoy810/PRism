from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.graph import ReviewGraph
from app.models.review import (
    PostReviewRequest,
    ReviewIssue,
    ReviewRequest,
    ReviewResult,
    ReviewStats,
)
from app.services.diff import build_position_map
from app.services.github import fetch_pr_context, parse_pr_url
from app.services.github_review import post_review_to_github
from app.services.llm import stream_analyze_pr

router = APIRouter()


@router.get("/pr/meta")
async def get_pr_meta(
    pr_url: str = Query(...),
    github_token: str | None = Query(None),
):
    try:
        owner, repo, pr_number = parse_pr_url(pr_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        ctx = await fetch_pr_context(owner, repo, pr_number, github_token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {str(e)}")

    return {
        "code": "0",
        "data": {
            "pr_title": ctx["title"],
            "author_name": ctx["author_name"],
            "author_avatar": ctx["author_avatar"],
            "updated_at": ctx["updated_at"],
            "created_at": ctx.get("created_at", ""),
            "commits": ctx["commits"],
            "base_branch": ctx["base_branch"],
            "head_branch": ctx["head_branch"],
            "additions": ctx["stats"].additions,
            "deletions": ctx["stats"].deletions,
            "files_changed": ctx["stats"].files_changed,
            "files": ctx.get("files_detail", []),
        },
    }


@router.post("/review")
async def create_review(request: ReviewRequest):
    try:
        graph = ReviewGraph()
        result = await graph.run(pr_url=request.pr_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review analysis error: {str(e)}")

    review_result = _graph_result_to_review_result(result, request.pr_url)

    return {"code": "0", "message": "ok", "data": review_result.model_dump()}


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
        async for event_json in stream_analyze_pr(pr_context, perspective=request.perspective, model=request.model or "deepseek-v4-flash", api_key=request.api_key, base_url=request.base_url):
            yield f"data: {event_json}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _graph_result_to_review_result(graph_output: dict, pr_url: str) -> ReviewResult:
    issues = [
        ReviewIssue(**{k: v for k, v in issue.items() if k in ReviewIssue.model_fields})
        for issue in graph_output.get("issues", [])
    ]
    stats = ReviewStats(**graph_output.get("stats", {}))
    return ReviewResult(
        pr_url=pr_url,
        summary=graph_output.get("summary", ""),
        risk_level=graph_output.get("risk_level", "LOW"),
        issues=issues,
        stats=stats,
    )


@router.post("/review/post")
async def post_review(request: PostReviewRequest):
    try:
        owner, repo, pr_number = parse_pr_url(request.pr_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    import httpx

    from app.models.review import ReviewIssue, ReviewResult, ReviewStats

    stats = ReviewStats(**request.result.get("stats", {}))
    issues = [ReviewIssue(**i) for i in request.result.get("issues", [])]
    result = ReviewResult(
        pr_url=request.pr_url,
        summary=request.result.get("summary", ""),
        risk_level=request.result.get("risk_level", "LOW"),
        issues=issues,
        stats=stats,
    )

    try:
        pr_context = await fetch_pr_context(owner, repo, pr_number, request.github_token)
        position_map = build_position_map(pr_context["diff"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {str(e)}")

    try:
        data = await post_review_to_github(owner, repo, pr_number, request.github_token, result, position_map)
        return {"code": "0", "message": "ok", "data": {"html_url": data.get("html_url", "")}}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

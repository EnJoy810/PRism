import json
import os
import re
from openai import AsyncOpenAI
from app.models.review import ReviewIssue, ReviewResult, Severity

MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com/v1"

SYSTEM_PROMPT = """You are a senior software engineer conducting a thorough code review.
Your goal is to identify real issues, not style nitpicks.

Severity levels:
- ERROR: Logic bugs, security vulnerabilities, null pointer risks, data loss potential
- WARNING: Performance issues, non-idiomatic patterns, missing error handling
- INFO: Minor improvements, documentation suggestions (only if explicitly requested)

Rules:
1. Only report issues you are highly confident about (>85% confidence)
2. Anchor every issue to a specific file and line when possible
3. Provide actionable suggestions, not vague recommendations
4. If the diff looks correct, say so — silence on a file means it's fine
5. Never report INFO issues unless options.include_style is true"""

REVIEW_PROMPT_TEMPLATE = """PR Title: {title}
PR Description: {description}
Base branch: {base_branch} → {head_branch}

Changed files: {files}

Diff:
{diff}

Analyze this PR and return a JSON response with this exact structure:
{{
  "summary": "2-3 sentence summary of what this PR does and overall quality",
  "risk_level": "HIGH|MEDIUM|LOW",
  "issues": [
    {{
      "severity": "ERROR|WARNING|INFO",
      "file": "path/to/file.ts",
      "line": 42,
      "title": "Short issue title",
      "description": "Detailed explanation of the issue",
      "suggestion": "Specific fix suggestion"
    }}
  ]
}}

Return only valid JSON, no markdown fences."""


def _make_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=BASE_URL)


def _extract_json(text: str) -> str:
    text = text.strip()
    fence_m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if fence_m:
        return fence_m.group(1).strip()
    return text


def _build_prompt(pr_context: dict) -> str:
    return REVIEW_PROMPT_TEMPLATE.format(
        title=pr_context["title"],
        description=pr_context["description"][:500],
        base_branch=pr_context["base_branch"],
        head_branch=pr_context["head_branch"],
        files=", ".join(pr_context["files"][:20]),
        diff=pr_context["diff"][:80000],
    )


async def analyze_pr(pr_context: dict, include_style: bool = False) -> ReviewResult:
    client = _make_client()
    prompt = _build_prompt(pr_context)

    response = await client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        temperature=1.0,
        top_p=1.0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw = _extract_json(response.choices[0].message.content or "{}")
    data = json.loads(raw)

    issues = [ReviewIssue(**issue) for issue in data.get("issues", [])]

    if not include_style:
        issues = [i for i in issues if i.severity != Severity.INFO]

    stats = pr_context["stats"]
    stats.issues_by_severity = {
        "ERROR": sum(1 for i in issues if i.severity == Severity.ERROR),
        "WARNING": sum(1 for i in issues if i.severity == Severity.WARNING),
        "INFO": sum(1 for i in issues if i.severity == Severity.INFO),
    }

    return ReviewResult(
        pr_url=pr_context.get("pr_url", ""),
        summary=data.get("summary", ""),
        risk_level=data.get("risk_level", "LOW"),
        issues=issues,
        stats=stats,
    )


CURSOR_PATH_SYSTEM_PROMPT = """You are analyzing a code diff for a reviewer.
List the line numbers (1-indexed) that contain actual code changes.
Focus on +/- lines. Prioritize logic changes over imports/boilerplate.
Return a JSON array of integers, e.g. [5, 23, 8, 41]."""


def _fallback_cursor_path(diff_lines: list[str]) -> list[int]:
    add_del: list[int] = []
    other: list[int] = []
    for i, l in enumerate(diff_lines):
        stripped = l.lstrip()
        if stripped.startswith('--- ') or stripped.startswith('+++ ') or stripped.startswith('@@'):
            other.append(i + 1)
        elif l.startswith('+') or l.startswith('-'):
            add_del.append(i + 1)
        else:
            other.append(i + 1)
    return (add_del + other)[:15]


async def generate_cursor_path(diff_lines: list[str]) -> list[int]:
    client = _make_client()
    numbered = "\n".join(f"{i+1}: {line}" for i, line in enumerate(diff_lines))
    prompt = f"Diff lines:\n{numbered}\n\nReturn only a JSON array of the most interesting line numbers in reading order."

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            max_tokens=150,
            temperature=0.3,
            messages=[
                {"role": "system", "content": CURSOR_PATH_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        raw = _extract_json(response.choices[0].message.content or "[]")
        path = json.loads(raw)
        if isinstance(path, list) and len(path) > 0 and all(isinstance(i, int) for i in path):
            valid = [i for i in path if 1 <= i <= len(diff_lines)]
            if valid:
                return valid[:15]
    except Exception:
        pass

    return _fallback_cursor_path(diff_lines)


async def stream_analyze_pr(pr_context: dict):
    client = _make_client()
    prompt = _build_prompt(pr_context)

    stream = await client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        temperature=1.0,
        top_p=1.0,
        stream=True,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta

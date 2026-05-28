import json
import anthropic
from app.models.review import ReviewIssue, ReviewResult, Severity

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


async def analyze_pr(pr_context: dict, include_style: bool = False) -> ReviewResult:
    """Send PR context to Claude and parse structured review."""
    client = anthropic.AsyncAnthropic()

    prompt = REVIEW_PROMPT_TEMPLATE.format(
        title=pr_context["title"],
        description=pr_context["description"][:500],
        base_branch=pr_context["base_branch"],
        head_branch=pr_context["head_branch"],
        files=", ".join(pr_context["files"][:20]),
        diff=pr_context["diff"][:80000],
    )

    message = await client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text if message.content else "{}"
    data = json.loads(raw)

    issues = [ReviewIssue(**issue) for issue in data.get("issues", [])]

    # Severity gating: filter INFO unless include_style
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

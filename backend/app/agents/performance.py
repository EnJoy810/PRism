from app.agents.base import BaseAgent

SYSTEM_PROMPT = """You are a senior engineer reviewing a pull request for performance regressions.

Do NOT report issues found inside comments, docstrings, or string literals. Only report issues in executable code lines.

── Step 1: Observe resource-related changes ──
Do NOT guess intent yet. Read the diff literally and record:
- Which caches, batch operations, or connection pool management were removed or changed?
- Were any DB queries or IO calls added inside loops that iterate over unbounded data?
- Were bulk operations replaced with per-item operations?
- Were async non-blocking operations replaced with synchronous blocking calls?
- Was pagination or limiting removed from queries?

── Step 2: Quantify the regression ──
For each observed change:
- What was the time/space complexity before? What is it now?
- At what realistic data scale does this become a bottleneck?
- Is there a replacement optimization elsewhere in this diff?

── Step 3: Validate it is a real bottleneck ──
- Is this code path executed frequently under production load?
- Is the regression measurable, or purely theoretical?
- Does any existing mitigation (index, cache, rate limit) already cover this?

── Step 4: Calibrate confidence with intent ──
Only now consider the PR's stated intent. Lower confidence if the change is an intentional
trade-off, but still report if no replacement optimization is present.

── Step 5: Report or skip ──
Report only performance issues backed by concrete scale reasoning (e.g. "this adds one DB query
per item in a list that can have N rows"). Skip micro-optimizations with no bottleneck evidence.

Severity:
- ERROR: Definite performance collapse at realistic scale (N+1 query, memory leak, deadlock)
- WARNING: Will become a bottleneck at specific data volumes
- INFO: Minor optimization suggestion (default: do not report)

Respond in English."""


class PerformanceAgent(BaseAgent):
    category = "performance"
    system_prompt = SYSTEM_PROMPT

    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        ctx = context or {}
        pr_title = ctx.get("pr_title", "")
        pr_description = ctx.get("pr_description", "")
        files = ctx.get("files", [])
        symbol_defs = ctx.get("symbol_definitions", {})

        parts = ["Review the following PR diff for performance regressions:"]
        if pr_title:
            parts.append(f"PR title: {pr_title}")
        if pr_description:
            parts.append(f"PR description: {pr_description[:500]}")
        if files:
            parts.append(f"Changed files: {', '.join(files[:20])}")
        if symbol_defs:
            def_lines = ["\nReferenced symbol definitions:"]
            for sym, defn in list(symbol_defs.items())[:5]:
                def_lines.append(f"\n--- {sym} ---\n{defn}")
            parts.append("".join(def_lines))
        blast_section = ctx.get("blast_radius_section", "")
        if blast_section:
            parts.append(blast_section)
            parts.append(
                "\n---\n[CROSS-FILE CONTEXT] shows callers of the changed functions. "
                "Check each caller for performance issues introduced by the change (e.g. repeated calls in loops). "
                'Set evidence_source to "CONTEXT" and quote actual code from [CROSS-FILE CONTEXT].\n'
            )
        parts.append(f"\n[DIFF]\n{diff[:40000]}")
        parts.append(
            "\n\nFirst write <think> with your analysis, then output JSON:\n"
            '{"findings": [{"file": "path", "line": line_or_null, "title": "short title", '
            '"description": "what performance regression this introduces, '
            'at what data scale it triggers, and the impact", '
            '"severity": "ERROR|WARNING|INFO", '
            '"confidence": 0.0_to_1.0, "category": "performance", '
            '"impact_type": "n_plus_one|memory_leak|complexity_increase|blocking_io|resource_leak|info_only", '
            '"impact_statement": "concrete scale at which this becomes a bottleneck", '
            '"evidence_source": "DIFF|CONTEXT", '
            '"evidence": ["quoted code snippets that show the regression"]}]}'
        )
        return "\n".join(parts)

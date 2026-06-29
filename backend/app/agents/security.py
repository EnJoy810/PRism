from app.agents.base import BaseAgent

SYSTEM_PROMPT = """You are a senior security engineer reviewing a pull request for security vulnerabilities introduced by the diff.

Do NOT report issues found inside comments, docstrings, or string literals. Only report issues in executable code lines.

── Step 1: Observe what changed ──
Do NOT guess intent yet. Read the diff literally and record:
- Which input validation, permission checks, or auth guards were removed or weakened?
- Which untrusted inputs now reach sinks (DB queries, shell commands, HTML output, file paths)?
- Which secrets, tokens, or credentials are now logged, exposed, or compared insecurely?
- Which cryptographic operations were removed, downgraded, or replaced?

── Step 2: Trace the attack path ──
For each observed change, ask:
- What did this mechanism protect against before?
- Now that it is gone or weakened, what can an attacker do?
- What input does the attacker control? What is the worst-case outcome?
- Is there a replacement defense elsewhere in this diff? If yes, skip. If no, proceed.

── Step 3: Validate exploitability ──
Before reporting, confirm:
- Is there a concrete, realistic attack scenario (not just theoretical)?
- What preconditions does the attacker need? Are they achievable?
- Does any other layer already mitigate this (e.g., WAF, upstream validation)?

── Step 4: Calibrate confidence with intent ──
Only now consider the PR's stated intent.
- If a security mechanism is intentionally replaced with an equivalent one → do not report.
- If the change looks intentional but has no replacement defense → lower confidence but still report.

── Step 5: Report or skip ──
Report only findings with a concrete attack path. Skip: style issues, theoretical risks requiring
unrealistic assumptions, or changes where a replacement defense is clearly present.

Severity:
- ERROR: Directly exploitable, clear attack path (SQLi, auth bypass, SSRF, XSS, RCE)
- WARNING: Exploitable under specific conditions
- INFO: Security best-practice violation only (default: do not report)

Respond in English."""


class SecurityAgent(BaseAgent):
    category = "security"
    system_prompt = SYSTEM_PROMPT

    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        ctx = context or {}
        pr_title = ctx.get("pr_title", "")
        pr_description = ctx.get("pr_description", "")
        files = ctx.get("files", [])
        symbol_defs = ctx.get("symbol_definitions", {})

        parts = ["Review the following PR diff for security vulnerabilities:"]
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
                "Check each caller individually. If a caller is affected by the change "
                "(e.g., missing validation, auth bypass), you may report it, but set "
                'evidence_source to "CONTEXT" and quote the actual code from [CROSS-FILE CONTEXT].\n'
            )
        parts.append(f"\n[DIFF]\n{diff[:40000]}")
        parts.append(
            "\n\nFirst write <think> with your analysis, then output JSON:\n"
            '{"findings": [{"file": "path", "line": line_or_null, "title": "short title", '
            '"description": "what security risk this change introduces, the attack path, and the impact", '
            '"severity": "ERROR|WARNING|INFO", '
            '"confidence": 0.0_to_1.0, "category": "security", '
            '"impact_type": "injection|auth_bypass|info_disclosure|security_regression|info_only", '
            '"impact_statement": "concrete attack scenario and worst-case outcome", '
            '"evidence_source": "DIFF|CONTEXT", '
            '"evidence": ["quoted code snippets from the diff or context that support this finding"]}]}'
        )
        return "\n".join(parts)

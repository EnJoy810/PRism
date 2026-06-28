from app.agents.base import BaseAgent

SYSTEM_PROMPT = """You are a senior software engineer reviewing a pull request for logic bugs and correctness errors.

Your job: find places where the new code does NOT do what it is supposed to do.

── Before you start: what NOT to report ──
Do NOT report anything a linter or formatter can catch automatically:
- Naming conventions (variable names, function names, casing)
- Code style, indentation, formatting
- Missing or redundant comments / docstrings
- Import order or organization
- Line length violations
- Unused variables that a linter would flag
These belong in linter config, not code review. Report ONLY behavioral bugs.

── Step 1: For each changed function or block, ask three questions ──
  (a) What did this code do BEFORE the change?
  (b) What does it do NOW after the change?
  (c) Is the new behavior correct? Are there inputs or states where it produces a wrong result?

This is the only question that matters. Do not hunt for "categories of issues" — hunt for
cases where behavior (b) diverges from what callers and users expect.

── Step 2: Specifically look for these high-frequency bug patterns ──
Work through each pattern explicitly. Skip only if clearly not present.

  WRONG VARIABLE / VALUE
  - Is the correct variable used? (e.g. endTime vs startTime, slotEnd vs slotStart)
  - Are constants or literals correct? (off-by-one, wrong default)

  INVERTED / WRONG CONDITION
  - Is the boolean condition inverted? (should be `>` but wrote `<`, should be `||` but wrote `&&`)
  - Can a branch be unreachable due to a condition that is always true or always false?
  - Is a guard removed that was protecting a code path?

  MISSING AWAIT / UNHANDLED ASYNC
  - Is an async function called without `await` inside a loop or callback?
  - Is a Promise returned but never awaited, causing fire-and-forget behavior?
  - Does forEach/map receive an async callback whose result is ignored?

  NULL / UNDEFINED ACCESS
  - Is a value accessed without a null/undefined check after the change?
  - Is optional chaining (`?.`) added or removed in a way that changes behavior?
  - Can a function now return null where callers expect a value?

  INTERFACE / CONTRACT BREAK
  - Did a function signature change (added/removed parameters)?
  - Does the existing callers still pass the right arguments?
  - Did a return type change in a way that breaks callers?
  - Does a class still implement its interface after the change?

  CONCURRENCY / RACE CONDITION
  - Can two concurrent requests pass a check and both modify shared state?
  - Is a read-modify-write sequence now non-atomic?
  - Is a lazy initialization pattern now unsafe under concurrency?

── Step 3: Validate before reporting ──
For each potential finding:
- What is the exact code line that is wrong?
- What concrete input or scenario triggers the bug?
- Is there a replacement fix elsewhere in the diff? If yes, skip.

── Step 4: Calibrate confidence ──
Only now consider the PR's stated intent. Lower confidence if the change looks intentional,
but still report if no replacement logic is present.

── Step 5: Report or skip ──
Report only bugs where you can point to a specific line and explain the wrong behavior.
Skip: style, naming, comments, documentation, pure refactors with equivalent behavior.

Severity:
- ERROR: Causes incorrect behavior, data loss, or runtime crash
- WARNING: Wrong behavior under specific inputs or race conditions
- INFO: Minor issue (default: do not report)

Respond in English."""


class QualityAgent(BaseAgent):
    category = "quality"
    system_prompt = SYSTEM_PROMPT

    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        ctx = context or {}
        pr_title = ctx.get("pr_title", "")
        pr_description = ctx.get("pr_description", "")
        files = ctx.get("files", [])
        symbol_defs = ctx.get("symbol_definitions", {})

        parts = [
            "Review the following PR diff for logic bugs and correctness errors.",
            "Focus: wrong variable, inverted condition, missing await, null dereference, interface break, race condition.",
        ]
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
                "Check each caller for argument mismatches, null pointer risks, or behavior regressions. "
                'Set evidence_source to "CONTEXT" and quote actual code from [CROSS-FILE CONTEXT].\n'
            )
        parts.append(f"\n[DIFF]\n{diff[:40000]}")
        parts.append(
            "\n\nFirst write <think> going through each bug pattern from the instructions, "
            "then output JSON:\n"
            '{"findings": [{"file": "path", "line": line_or_null, "title": "short title", '
            '"description": "what is wrong: the exact incorrect behavior, what input triggers it, and what goes wrong", '
            '"severity": "ERROR|WARNING|INFO", '
            '"confidence": 0.0_to_1.0, "category": "quality", '
            '"impact_type": "runtime_error|behavior_regression|api_breakage|async_misuse|null_deref|race_condition|style_only", '
            '"impact_statement": "concrete scenario where this causes incorrect behavior", '
            '"evidence_source": "DIFF|CONTEXT", '
            '"evidence": ["quoted code snippets that show the bug"]}]}'
        )
        return "\n".join(parts)

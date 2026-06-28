import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path

from json_repair import repair_json

from app.agents.judge import JudgeAgent
from app.agents.performance import PerformanceAgent
from app.agents.quality import QualityAgent
from app.agents.security import SecurityAgent
from app.models.agent import AgentResult, AgentStatus, FindingSchema
from app.services.evidence import publication_gate, severity

logger = logging.getLogger(__name__)

_BATCH_SIZE = 30
_TOKEN_CHARS = 4
_PER_FILE_TOKEN_THRESHOLD = 8000
_PER_FILE_CONCURRENCY = 5

# 大 PR 主动降级阈值：超过此文件数时过滤掉非代码文件，只 review 核心逻辑
_LARGE_PR_FILE_THRESHOLD = 30

_SKIP_DIFF_FILE_PARTS = {"node_modules", "vendor", "dist", ".git"}
_SKIP_DIFF_FILE_SUFFIXES = {".lock", ".sum", ".lockb"}
_SKIP_DIFF_FULL_NAMES = {
    "package-lock.json", "pnpm-lock.yaml", "poetry.lock",
    "Gemfile.lock", "requirements.txt", "Makefile",
}
_SKIP_DIFF_FILE_NAMES_START = {"test_"}
_SKIP_DIFF_FILE_NAMES_END = {
    ".test.ts", ".spec.ts", ".test.js", ".spec.js",
    "_test.py", ".test.py",
}

# 大 PR 时额外跳过的非代码文件后缀
_SKIP_LARGE_PR_SUFFIXES = {
    ".md", ".mdx", ".txt", ".rst",           # 文档
    ".json", ".yaml", ".yml", ".toml",        # 配置（lock 文件已在上方处理）
    ".env", ".env.example",                   # 环境变量
    ".sh", ".bat", ".ps1",                    # 脚本
    ".svg", ".png", ".jpg", ".ico", ".gif",  # 图片
    ".css", ".scss", ".less",                 # 纯样式（无逻辑）
}

_SKIP_LARGE_PR_FULL_NAMES = {
    "CHANGELOG.md", "CHANGELOG", "LICENSE", "LICENSE.md",
    "CLAUDE.md", "AGENTS.md", ".gitignore", ".dockerignore",
    ".eslintrc", ".prettierrc", "tsconfig.json", "jest.config.js",
    "vite.config.ts", "vite.config.js",
}


def _should_skip_large_pr_file(filepath: str) -> bool:
    """大 PR 模式下额外跳过的非核心文件。"""
    name = Path(filepath).name
    if name in _SKIP_LARGE_PR_FULL_NAMES:
        return True
    suffix = Path(filepath).suffix.lower()
    if suffix in _SKIP_LARGE_PR_SUFFIXES:
        return True
    return False


def _should_skip_diff_file(filepath: str) -> bool:
    parts = filepath.split("/")
    if any(p in _SKIP_DIFF_FILE_PARTS for p in parts):
        return True
    if any(filepath.endswith(s) for s in _SKIP_DIFF_FILE_SUFFIXES):
        return True
    if Path(filepath).name in _SKIP_DIFF_FULL_NAMES:
        return True
    name = Path(filepath).name
    if any(name.startswith(s) for s in _SKIP_DIFF_FILE_NAMES_START):
        return True
    if any(name.endswith(s) for s in _SKIP_DIFF_FILE_NAMES_END):
        return True
    return False


class ReviewGraph:
    def __init__(self):
        self._security_agent: SecurityAgent | None = None
        self._performance_agent: PerformanceAgent | None = None
        self._quality_agent: QualityAgent | None = None
        self._judge: JudgeAgent | None = None

    @property
    def security_agent(self) -> SecurityAgent:
        if self._security_agent is None:
            self._security_agent = SecurityAgent()
        return self._security_agent

    @property
    def performance_agent(self) -> PerformanceAgent:
        if self._performance_agent is None:
            self._performance_agent = PerformanceAgent()
        return self._performance_agent

    @property
    def quality_agent(self) -> QualityAgent:
        if self._quality_agent is None:
            self._quality_agent = QualityAgent()
        return self._quality_agent

    @property
    def judge(self) -> JudgeAgent:
        if self._judge is None:
            self._judge = JudgeAgent()
        return self._judge

    async def fetch_pr_context(self, pr_url: str) -> dict:
        from app.services.github import fetch_pr_context as github_fetch_context
        from app.services.github import parse_pr_url
        owner, repo, pr_number = parse_pr_url(pr_url)
        ctx = await github_fetch_context(owner, repo, pr_number)
        ctx["pr_url"] = pr_url
        if ctx.get("diff_truncated"):
            logger.warning("diff truncated >100KB for %s — coverage may be partial", pr_url)
        return ctx

    async def _fetch_pr_context(self, pr_url: str, github_token: str | None = None) -> dict:
        from app.services.github import fetch_pr_context as github_fetch_context
        from app.services.github import parse_pr_url

        if github_token is None:
            return await self.fetch_pr_context(pr_url)
        owner, repo, pr_number = parse_pr_url(pr_url)
        ctx = await github_fetch_context(owner, repo, pr_number, github_token)
        ctx["pr_url"] = pr_url
        if ctx.get("diff_truncated"):
            logger.warning("diff truncated >100KB for %s — coverage may be partial", pr_url)
        return ctx

    async def run(
        self,
        pr_url: str,
        context: dict | None = None,
        github_token: str | None = None,
        event: str = "",
    ) -> dict:
        t0 = time.monotonic()
        if context is None:
            context = await self._fetch_pr_context(pr_url, github_token)
        if github_token:
            context["github_token"] = github_token
        logger.info("fetch_context done: %s — %.2fs", pr_url, time.monotonic() - t0)

        symbol_task = asyncio.create_task(self._fetch_symbol_context(context, pr_url))
        blast_task = asyncio.create_task(self._fetch_blast_radius(context, pr_url))
        sast_task = asyncio.create_task(self._fetch_sast_findings(context, pr_url))
        verification_task = asyncio.create_task(self._fetch_verification(context, pr_url))

        investigate_start = time.monotonic()
        logger.info("investigate started: symbol_context, blast_radius, sast, verification")
        symbol_defs, blast_radius, sast_findings, verification = await asyncio.gather(
            symbol_task, blast_task, sast_task, verification_task, return_exceptions=True
        )

        context["symbol_definitions"] = symbol_defs if isinstance(symbol_defs, dict) else {}
        context["blast_radius"] = blast_radius if isinstance(blast_radius, list) else []
        context["sast_findings"] = sast_findings if isinstance(sast_findings, dict) else {}
        context["verification"] = verification if isinstance(verification, dict) else {}
        logger.info(
            "investigate done: symbols=%d blast_groups=%d sast=%d verification_keys=%d %.2fs",
            len(context["symbol_definitions"]),
            len(context["blast_radius"]),
            sum(len(v) for v in context["sast_findings"].values()),
            len(context["verification"]),
            time.monotonic() - investigate_start,
        )

        diff = context.get("diff", "")
        diff_tokens = _estimated_tokens(diff)
        context["_event"] = event

        if diff_tokens > _PER_FILE_TOKEN_THRESHOLD:
            logger.info("diff tokens %d > %d — per-file parallel", diff_tokens, _PER_FILE_TOKEN_THRESHOLD)
            return await self._run_per_file(context, pr_url, t0, event=event)

        needs_batching = (
            context.get("diff_truncated", False)
            or len(context.get("files", [])) > _BATCH_SIZE
            or diff_tokens > _max_tokens_per_call()
        )
        if not needs_batching:
            return await self._run_single(context, pr_url, t0, event=event)

        return await self._run_multi(context, pr_url, t0, event=event)

    async def _fetch_symbol_context(self, context: dict, pr_url: str) -> dict[str, str]:
        try:
            from app.services.context import fetch_symbol_context
            from app.services.github import parse_pr_url

            owner, repo, _ = parse_pr_url(pr_url)
            ref = context.get("head_branch", "")
            files = context.get("files", [])
            diff = context.get("diff", "")
            return await fetch_symbol_context(
                owner,
                repo,
                ref,
                files,
                diff,
                token=context.get("github_token"),
            )
        except Exception as e:
            logger.warning("Symbol context fetch failed: %s", e)
            return {}

    async def _fetch_blast_radius(self, context: dict, pr_url: str) -> list:
        try:
            from app.config import load_config
            from app.services.blast_radius import (
                compute_blast_radius,
                compute_blast_radius_codegraph,
            )
            from app.services.github import parse_pr_url
            from app.services.indexer import build_index, ensure_index_schema
            from app.services.repo import ensure_repo

            owner, repo, pr_number = parse_pr_url(pr_url)

            cfg = load_config()
            if not cfg.review.callgraph_enabled:
                logger.info("blast_radius[skip]: callgraph_enabled=false — %s", pr_url)
                return []

            head_sha = context.get("head_sha", "")
            if not head_sha:
                logger.info("blast_radius[skip]: no head_sha in context — %s", pr_url)
                return []

            token = context.get("github_token") or cfg.github_token or os.environ.get("GITHUB_TOKEN", "")
            if not token:
                logger.info("blast_radius[skip]: no github token — %s", pr_url)
                return []

            repo_path = await ensure_repo(owner, repo, head_sha, token)
            if repo_path is None:
                logger.info(
                    "blast_radius[degraded]: clone failed for %s/%s@%s — diff-only fallback",
                    owner, repo, head_sha[:8],
                )
                return []

            diff = context.get("diff", "")
            changed_fns = _extract_changed_functions(diff)
            diff_tokens = len(diff) // 4

            backend = cfg.review.callgraph_backend
            if backend == "codegraph":
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    compute_blast_radius_codegraph,
                    repo_path, changed_fns, diff_tokens,
                )
                logger.info(
                    "blast_radius[ok/codegraph]: changed_fns=%d caller_groups=%d — %s",
                    len(changed_fns), len(result), pr_url,
                )
                return result

            # builtin backend (default)
            db_path = repo_path.parent / f"{repo_path.name}.db"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, build_index, repo_path, db_path)
            await loop.run_in_executor(None, ensure_index_schema, db_path)

            changed_node_ids = _changed_node_ids_from_diff(db_path, diff)
            if not changed_fns and not changed_node_ids:
                logger.info(
                    "blast_radius[skip]: no changed functions/nodes extracted from diff — %s",
                    pr_url,
                )
                return []

            result = compute_blast_radius(
                db_path,
                changed_fns,
                diff_tokens,
                changed_node_ids=changed_node_ids,
            )

            # Supplement BFS with call sites found directly in the diff.
            # Handles new functions whose callers couldn't be import-resolved.
            from app.services.blast_radius import find_new_callers_in_diff
            diff_callers = find_new_callers_in_diff(diff)
            bfs_fns = {item["changed_fn"].rsplit(":", 1)[-1] for item in result}
            added_from_diff = 0
            for item in diff_callers:
                fn_short = item["changed_fn"].rsplit(":", 1)[-1]
                if fn_short not in bfs_fns:
                    result.append(item)
                    added_from_diff += 1

            logger.info(
                "blast_radius[ok/builtin]: changed_fns=%d changed_nodes=%d "
                "caller_groups=%d diff_callers=%d — %s",
                len(changed_fns), len(changed_node_ids),
                len(result), added_from_diff, pr_url,
            )
            return result

        except Exception as e:
            logger.warning(
                "blast_radius[error]: %s: %s — %s",
                type(e).__name__, e, pr_url,
            )
            return []

    async def _run_caller_parameter_check(
        self,
        blast_radius: list[dict],
        diff: str,
        max_callers_per_fn: int = 3,
        max_functions: int = 5,
    ) -> list[FindingSchema]:
        """Proactive check: do callers pass arguments that the changed function mishandles?

        Unlike _run_impact_verification (which requires a finding first), this pass
        works without any prior finding. It looks at each changed function's diff chunk
        alongside its callers and asks a narrow question: "does any caller pass a value
        the function doesn't handle correctly?"

        This catches caller-aware bugs like None-key collisions that are invisible when
        the function is analyzed in isolation.
        """
        from app.services.llm import LLMClient

        if not blast_radius or not diff:
            return []

        # Build file→diff-chunk map so we can show the actual function body
        file_diffs = split_diff_by_file(diff)

        llm = LLMClient()
        new_findings: list[FindingSchema] = []

        async def check_one(item: dict) -> list[FindingSchema]:
            changed_fn: str = item.get("changed_fn", "")
            callers = item.get("callers", [])[:max_callers_per_fn]
            if not callers or ":" not in changed_fn:
                return []

            fn_file, fn_short = changed_fn.rsplit(":", 1)
            fn_diff_chunk = file_diffs.get(fn_file, "")
            if not fn_diff_chunk:
                return []

            call_site_sections = []
            for caller in callers:
                snippet = _extract_call_site(caller.get("code", ""), fn_short)
                call_site_sections.append(
                    f"[Caller] {caller['file']}:{caller['start_line']} `{caller['fn']}`\n"
                    f"```\n{snippet}\n```"
                )

            prompt = (
                f"A function `{fn_short}` in `{fn_file}` was changed.\n\n"
                f"[FUNCTION DIFF]\n```diff\n{fn_diff_chunk[:1200]}\n```\n\n"
                f"[CALLERS]\n"
                + "\n\n".join(call_site_sections)
                + "\n\n"
                "Question: Does any caller pass an argument value that this function "
                "does not handle correctly? Look ONLY for:\n"
                "- None/null/undefined passed where the function expects a non-null value\n"
                "- Wrong type passed (str vs int, dict vs list, etc.)\n"
                "- Missing required argument\n"
                "- Value used as a dict key or array index without validation\n\n"
                "Output JSON only. If no problem:\n"
                '{"issues": []}\n'
                "If a problem exists:\n"
                '{"issues": [{"caller_file": "path", "caller_fn": "name", '
                '"line": N, "arg": "argument expression", '
                '"reason": "one sentence why this causes a problem"}]}'
            )

            try:
                response = await llm.chat(
                    messages=[
                        {"role": "system", "content": (
                            "You are a strict code analyst. "
                            "Report ONLY issues where a caller passes an argument value "
                            "that the changed function clearly mishandles. "
                            "Do not speculate. Only report if the function code shows "
                            "the value would cause an error or wrong behavior. "
                            "Output valid JSON only."
                        )},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=512,
                    temperature=0.0,
                )
            except Exception as e:
                logger.debug("caller_parameter_check llm error: %s", e)
                return []

            try:
                content = response or ""
                logger.debug("caller_parameter_check raw response for %s: %s", changed_fn, content[:200])
                data = json.loads(repair_json(content))
                issues = data.get("issues", [])
            except Exception as e:
                logger.debug("caller_parameter_check parse error for %s: %s", changed_fn, e)
                return []

            results = []
            for issue in issues:
                caller_file = issue.get("caller_file", "")
                caller_fn = issue.get("caller_fn", "")
                arg = issue.get("arg", "")
                reason = issue.get("reason", "")
                line = issue.get("line")
                if not (caller_file and reason):
                    continue
                arg_label = f" (arg: `{arg}`)" if arg else ""
                results.append(FindingSchema(
                    file=caller_file,
                    line=line,
                    title=f"Caller passes invalid argument to `{fn_short}`{arg_label}",
                    description=(
                        f"`{caller_fn}` in `{caller_file}` calls `{fn_short}` "
                        f"with a value the function does not handle: {reason}"
                    ),
                    severity="WARNING",
                    confidence=0.75,
                    category="quality",
                    impact_type="runtime_error",
                    impact_statement=f"Calling `{fn_short}` with this argument may cause a runtime error.",
                    evidence=[reason],
                    evidence_source="CONTEXT",
                ))
            return results

        # Layer 1: AST gate — only check functions with unsafe param sinks
        # (dict key, array index, attribute deref without prior None guard).
        # Converts LLM task from "归因 (attribution)" to "验证 (verification)",
        # keeping precision stable while avoiding subgraph noise.
        from app.services.blast_radius import detect_unsafe_param_sinks

        items_to_check = []
        for item in blast_radius:
            if not item.get("callers") or ":" not in item.get("changed_fn", ""):
                continue
            fn_file = item["changed_fn"].rsplit(":", 1)[0]
            fn_diff_chunk = file_diffs.get(fn_file, "")
            if fn_diff_chunk and detect_unsafe_param_sinks(fn_diff_chunk):
                items_to_check.append(item)
            if len(items_to_check) >= max_functions:
                break

        if not items_to_check:
            logger.info("caller_parameter_check: no eligible blast_radius items (AST gate filtered all)")
            return []

        logger.info("caller_parameter_check: checking %d functions", len(items_to_check))
        results_nested = await asyncio.gather(
            *[check_one(item) for item in items_to_check],
            return_exceptions=True,
        )
        for r in results_nested:
            if isinstance(r, list):
                new_findings.extend(r)
        logger.info("caller_parameter_check: done — %d findings", len(new_findings))
        return new_findings

    async def _run_impact_verification(
        self,
        findings: list[FindingSchema],
        blast_radius: list[dict],
        max_callers_per_fn: int = 3,
    ) -> list[FindingSchema]:
        """Second-pass: for each finding, check if its callers are also affected.

        This is the "finding-first" pattern: instead of pre-loading all caller code into
        the review prompt (which inflates FP), we first find issues in the diff, then ask
        a narrow, targeted question — "does THIS specific issue also impact these callers?"

        Only generates new FindingSchema entries for callers that are verifiably impacted.
        """
        from app.services.llm import LLMClient

        # Build a lookup: changed_file → list of blast_radius items.
        # Since blast_radius v2 fix, changed_fn is always "file:name" format.
        # Guard against old-format items (no ":" means no file info → skip with a warning).
        file_to_blast: dict[str, list[dict]] = {}
        skipped_no_file = 0
        for item in blast_radius:
            changed_fn: str = item.get("changed_fn", "")
            if ":" in changed_fn:
                file_part = changed_fn.rsplit(":", 1)[0]
                file_to_blast.setdefault(file_part, []).append(item)
            else:
                skipped_no_file += 1

        if skipped_no_file:
            logger.warning(
                "impact_verification: %d blast_radius items have no file prefix — skipped",
                skipped_no_file,
            )

        blast_files = set(file_to_blast.keys())
        finding_files = {f.file for f in findings}
        matched_files = blast_files & finding_files
        logger.info(
            "impact_verification: blast_groups=%d blast_files=%d finding_files=%d matched_files=%d",
            len(blast_radius), len(blast_files), len(finding_files), len(matched_files),
        )

        if not file_to_blast:
            logger.info("impact_verification: no blast items with file info — skipping")
            return []

        llm = LLMClient()
        new_findings: list[FindingSchema] = []

        async def check_one(finding: FindingSchema, item: dict) -> list[FindingSchema]:
            callers = item.get("callers", [])[:max_callers_per_fn]
            if not callers:
                return []

            changed_fn = item.get("changed_fn", "")
            fn_short = changed_fn.rsplit(":", 1)[-1] if ":" in changed_fn else changed_fn

            # Build call-site snippets (narrow: ±5 lines around the actual call)
            call_site_sections = []
            for caller in callers:
                snippet = _extract_call_site(caller.get("code", ""), fn_short)
                call_site_sections.append(
                    f"[Caller] {caller['file']}:{caller['start_line']} `{caller['fn']}`\n"
                    f"```\n{snippet}\n```"
                )

            prompt = (
                f"A code change was made to `{changed_fn}`.\n"
                f"The following issue was found in that function:\n\n"
                f"  [{finding.severity}] {finding.title}\n"
                f"  {finding.description}\n\n"
                f"Below are the call sites where this function is called from other files.\n"
                f"For EACH call site, determine: does the caller pass arguments or use the "
                f"return value in a way that would trigger or be affected by this issue?\n\n"
                + "\n\n".join(call_site_sections)
                + "\n\nOutput JSON only:\n"
                '{"impacts": [{"file": "path", "fn": "caller_fn", "line": N, '
                '"reason": "why this caller is affected"}]}\n'
                'If no callers are affected, output {"impacts": []}'
            )

            try:
                response = await llm.chat(
                    messages=[
                        {"role": "system", "content": (
                            "You are a precise code impact analyst. "
                            "Only report a caller as impacted if there is a direct, "
                            "concrete reason based on the code shown. "
                            "Do not speculate. Output valid JSON only."
                        )},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=512,
                    temperature=0.0,
                )
            except Exception as e:
                logger.debug("impact_verification llm error: %s", e)
                return []

            import json

            from json_repair import repair_json
            try:
                content = response.choices[0].message.content or ""
                data = json.loads(repair_json(content))
                impacts = data.get("impacts", [])
            except Exception:
                return []

            results = []
            for imp in impacts:
                imp_file = imp.get("file", "")
                imp_fn = imp.get("fn", "")
                imp_line = imp.get("line")
                reason = imp.get("reason", "")
                if not (imp_file and reason):
                    continue
                results.append(FindingSchema(
                    file=imp_file,
                    line=imp_line,
                    title=f"Cross-file impact: {finding.title}",
                    description=(
                        f"The issue in `{changed_fn}` propagates to caller `{imp_fn}`: "
                        f"{reason}"
                    ),
                    severity=_downgrade_severity(finding.severity),
                    confidence=min(finding.confidence * 0.85, 0.9),
                    category=finding.category,
                    impact_type=finding.impact_type,
                    impact_statement=finding.impact_statement,
                    evidence=[reason],
                    evidence_source="CONTEXT",
                ))
            return results

        # Match each finding to its blast_radius item and run checks concurrently
        tasks = []
        for finding in findings:
            items = file_to_blast.get(finding.file, [])
            for item in items:
                tasks.append(check_one(finding, item))

        logger.info(
            "impact_verification: spawning %d checks (findings=%d matched_blast_items=%d)",
            len(tasks), len(findings), sum(len(file_to_blast.get(f.file, [])) for f in findings),
        )
        if not tasks:
            logger.info(
                "impact_verification: 0 tasks — no findings overlap with blast_radius files. "
                "blast_files=%s, finding_files=%s",
                sorted(blast_files)[:5], sorted(finding_files)[:5],
            )
            return []

        results_nested = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results_nested:
            if isinstance(r, list):
                new_findings.extend(r)
        logger.info("impact_verification: done — %d cross-file findings", len(new_findings))
        return new_findings

    async def _fetch_sast_findings(self, context: dict, pr_url: str) -> dict[str, list[dict]]:
        try:
            from app.config import load_config
            from app.services.github import parse_pr_url
            from app.services.repo import ensure_repo
            from app.services.sast import run_sast

            owner, repo, _ = parse_pr_url(pr_url)
            head_sha = context.get("head_sha", "")
            if not head_sha:
                return {"security": [], "quality": []}

            cfg = load_config()
            token = context.get("github_token") or cfg.github_token or os.environ.get("GITHUB_TOKEN", "")
            if not token:
                return {"security": [], "quality": []}

            repo_path = await ensure_repo(owner, repo, head_sha, token)
            if repo_path is None:
                return {"security": [], "quality": []}

            files = context.get("files", [])
            if not files:
                return {"security": [], "quality": []}

            diff = context.get("diff", "")
            sec, qual = await asyncio.gather(
                run_sast(files, "security", repo_path, diff=diff),
                run_sast(files, "quality", repo_path, diff=diff),
                return_exceptions=True,
            )

            return {
                "security": sec if isinstance(sec, list) else [],
                "quality": qual if isinstance(qual, list) else [],
            }

        except Exception as e:
            logger.debug("sast fetch failed: %s", e)
            return {"security": [], "quality": []}

    async def _fetch_verification(self, context: dict, pr_url: str) -> dict:
        try:
            from app.config import load_config
            from app.services.github import parse_pr_url
            from app.services.repo import ensure_repo
            from app.services.verifier import verify_diff_imports

            owner, repo, _ = parse_pr_url(pr_url)
            head_sha = context.get("head_sha", "")
            if not head_sha:
                return {}

            cfg = load_config()
            token = context.get("github_token") or cfg.github_token or os.environ.get("GITHUB_TOKEN", "")
            if not token:
                return {}

            repo_path = await ensure_repo(owner, repo, head_sha, token)
            if repo_path is None:
                return {}

            diff = context.get("diff", "")
            if not diff:
                return {}

            return verify_diff_imports(repo_path, diff)

        except Exception as e:
            logger.debug("verification fetch failed: %s", e)
            return {}

    async def _run_single(self, context: dict, pr_url: str, t0: float, event: str = "") -> dict:
        diff = context.get("diff", "")
        agent_results = await self._run_agents(diff, context)
        return await self._assemble_result(agent_results, context, pr_url, t0, diff, event=event)

    async def _run_multi(self, context: dict, pr_url: str, t0: float, event: str = "") -> dict:
        batches = _split_into_batches(context, _BATCH_SIZE)
        logger.info(
            "multi-round: %d batches for %d files", len(batches), len(context.get("files", []))
        )

        all_agent_results: list[AgentResult] = []
        for i, batch in enumerate(batches):
            tb = time.monotonic()
            batch_diff = batch.get("diff", "")
            batch["symbol_definitions"] = context.get("symbol_definitions", {})
            agent_results = await self._run_agents(batch_diff, batch)
            logger.info(
                "batch %d/%d done: %d findings, %.2fs",
                i + 1, len(batches), sum(len(r.findings) for r in agent_results),
                time.monotonic() - tb,
            )
            all_agent_results.extend(agent_results)

        return await self._assemble_result(
            all_agent_results, context, pr_url, t0, context.get("diff", ""), event=event,
        )

    async def _run_per_file(self, context: dict, pr_url: str, t0: float, event: str = "") -> dict:
        diff = context.get("diff", "")
        file_diffs = split_diff_by_file(diff)

        # 基础过滤：始终跳过 node_modules / lock 文件等
        candidates = {f: d for f, d in file_diffs.items() if not _should_skip_diff_file(f)}

        # 大 PR 主动降级：超过阈值时额外过滤文档/配置/图片等非核心文件
        is_large_pr = len(candidates) > _LARGE_PR_FILE_THRESHOLD
        if is_large_pr:
            before = len(candidates)
            candidates = {f: d for f, d in candidates.items() if not _should_skip_large_pr_file(f)}
            logger.info(
                "per-file: large PR (%d files) — degraded mode, skipped %d non-code files, reviewing %d",
                len(file_diffs), before - len(candidates), len(candidates),
            )

        file_items = [{"file": f, "diff": d} for f, d in candidates.items()]
        logger.info(
            "per-file: %d files after filtering (skipped %d)",
            len(file_items), len(file_diffs) - len(file_items),
        )

        if not file_items:
            logger.warning("per-file: no files remain after filtering — falling back to full-diff")
            return await self._run_single(context, pr_url, t0, event=event)

        sem = asyncio.Semaphore(_PER_FILE_CONCURRENCY)

        async def _process_file(item: dict) -> list[AgentResult]:
            async with sem:
                file_ctx = {
                    **context,
                    "diff": item["diff"],
                    "files": [item["file"]],
                    # per-file 模式下去掉 PR description：
                    # 每个文件的 agent 只看局部 diff，完整 description 会导致
                    # "description 和这个文件不匹配"的重复噪声
                    "pr_description": "",
                }
                return await self._run_agents(item["diff"], file_ctx)

        tasks = [_process_file(item) for item in file_items]
        all_agent_results: list[AgentResult] = []
        for coro in asyncio.as_completed(tasks):
            try:
                results = await coro
                all_agent_results.extend(results)
            except Exception as e:
                logger.warning("unexpected per-file error: %s", e)

        if not all_agent_results:
            logger.warning("per-file: no agent results — falling back to full-diff")
            return await self._run_single(context, pr_url, t0, event=event)

        logger.info(
            "per-file done: %d files, %d agent results",
            len(file_items), len(all_agent_results),
        )
        return await self._assemble_result(
            all_agent_results, context, pr_url, t0, diff, event=event,
        )

    async def _run_agents(self, diff: str, context: dict) -> list[AgentResult]:
        sast_findings = context.get("sast_findings", {})

        # blast_radius is intentionally excluded here.
        # Cross-file callers are NOT pre-loaded into the review prompt; bulk-loading caller
        # code alongside the diff increases false positives without improving true positive
        # recall (tested: v6 diff-only P=45.7% vs v6 with callers P=30.4%).
        # Instead, caller context is used in a targeted second pass (_run_impact_verification)
        # that asks a specific question about each finding after the diff review is done.
        agent_context = {
            "pr_title": context.get("title", ""),
            "pr_description": context.get("description", ""),
            "files": context.get("files", []),
            "symbol_definitions": context.get("symbol_definitions", {}),
            "sast_findings": sast_findings,
        }

        ta = time.monotonic()
        security_task = self.security_agent.run(diff, agent_context)
        performance_task = self.performance_agent.run(diff, agent_context)
        quality_task = self.quality_agent.run(diff, agent_context)

        results: Sequence[AgentResult | BaseException] = await asyncio.gather(
            security_task, performance_task, quality_task,
            return_exceptions=True,
        )
        logger.info("agents done: %.2fs", time.monotonic() - ta)
        agent_names = ["security", "performance", "quality"]
        agent_results: list[AgentResult] = []
        for r in results:
            if isinstance(r, Exception):
                agent_results.append(
                    AgentResult(status=AgentStatus.TIMEOUT, findings=[], error_message=str(r))
                )
            else:
                agent_results.append(r)

        succeeded = [r for r in agent_results if r.status == AgentStatus.SUCCESS]
        if not succeeded:
            deterministic_findings = _sast_findings(context.get("sast_findings", {}))
            deterministic_findings.extend(
                _verification_findings(context.get("verification", {}))
            )
            if deterministic_findings:
                logger.warning(
                    "all LLM agents failed; continuing with %d deterministic findings",
                    len(deterministic_findings),
                )
                return agent_results

            failed_msgs = [
                f"{name}({r.status}: {r.error_message})"
                for name, r in zip(agent_names, agent_results)
            ]
            raise RuntimeError(f"All agents failed — review aborted: {'; '.join(failed_msgs)}")

        return agent_results

    async def _assemble_result(
        self,
        agent_results: list[AgentResult],
        context: dict,
        pr_url: str,
        t0: float,
        diff: str | None = None,
        event: str = "",
    ) -> dict:
        tj = time.monotonic()
        sast_findings = _sast_findings(context.get("sast_findings", {}))
        if sast_findings:
            agent_results = [
                *agent_results,
                AgentResult(status=AgentStatus.SUCCESS, findings=sast_findings),
            ]
        verifier_findings = _verification_findings(context.get("verification", {}))
        if verifier_findings:
            agent_results = [
                *agent_results,
                AgentResult(status=AgentStatus.SUCCESS, findings=verifier_findings),
            ]
        judge_output = await self.judge.run(
            agent_results,
            diff=diff,
            verification=context.get("verification", {}),
        )
        logger.info("judge done: %.2fs", time.monotonic() - tj)

        raw_findings = judge_output["findings"]
        findings: list[FindingSchema] = [
            f if isinstance(f, FindingSchema) else FindingSchema(**f)
            for f in raw_findings
        ]
        before_gate = len(findings)
        findings = publication_gate(findings, diff or "")
        logger.info("publication gate done: %d -> %d findings", before_gate, len(findings))

        # Phase 2: targeted cross-file impact verification.
        # For each finding, check whether the changed function's callers are also affected.
        # This is done AFTER the diff-only review so we ask a specific question ("does
        # THIS finding propagate?") rather than asking the LLM to freely review caller code.
        blast_radius = context.get("blast_radius", [])
        if not blast_radius:
            logger.info("impact_verification: skipped (blast_radius empty)")
            logger.info("caller_parameter_check: skipped (blast_radius empty)")
        else:
            # Run both passes concurrently:
            # - impact_verification: finding-first (does this bug propagate to callers?)
            # - caller_parameter_check: proactive (do callers pass bad args to changed fns?)
            caller_findings = await self._run_caller_parameter_check(blast_radius, diff or "")
            if isinstance(caller_findings, list):
                findings = list(findings) + caller_findings

            if not findings:
                logger.info("impact_verification: skipped (no findings to match against)")
            else:
                impact_findings = await self._run_impact_verification(findings, blast_radius)
                if isinstance(impact_findings, list):
                    findings = list(findings) + impact_findings

        decision: str = judge_output["merge_recommendation"]
        if not findings:
            decision = "APPROVE"
        elif any(severity(f) == "ERROR" for f in findings):
            decision = "REQUEST_CHANGES"
        else:
            decision = "COMMENT"
        skipped = [
            f"agent_{i}({r.status}: {r.error_message})"
            for i, r in enumerate(agent_results)
            if r.status != AgentStatus.SUCCESS
        ]

        severity_counts = {"ERROR": 0, "WARNING": 0, "INFO": 0}
        for f in findings:
            sev = f.severity if isinstance(f.severity, str) else f.severity.value
            if sev in severity_counts:
                severity_counts[sev] += 1

        logger.info(
            "review complete: %s — %d issues, risk=%s, decision=%s, total=%.2fs",
            pr_url, len(findings), _risk_level(findings), decision, time.monotonic() - t0,
        )

        return {
            "summary": context.get("title", ""),
            "risk_level": _risk_level(findings),
            "issues": [_finding_to_dict(f) for f in findings],
            "stats": {
                "files_changed": len(context.get("files", [])),
                "additions": _get_stat(context, "additions"),
                "deletions": _get_stat(context, "deletions"),
                "issues_by_severity": severity_counts,
            },
            "evidence_gate_stats": {
                "before_gate": before_gate,
                "after_gate": len(findings),
                "filtered": before_gate - len(findings),
            },
            "merge_recommendation": decision,
            "skipped_agents": skipped,
            "diff": diff or "",
            "diff_truncated": context.get("diff_truncated", False),
            "event": event,
        }

    async def post_comment(
        self,
        result: dict,
        pr_url: str,
        github_token: str,
    ) -> dict | None:
        from app.models.review import ReviewIssue, ReviewResult, ReviewStats
        from app.services.github import parse_pr_url
        from app.services.github_review import dismiss_old_reviews, post_review_to_github

        owner, repo, pr_number = parse_pr_url(pr_url)

        issues = [
            ReviewIssue(**{k: v for k, v in issue.items() if k in ReviewIssue.model_fields})
            for issue in result.get("issues", [])
        ]
        stats = ReviewStats(**result.get("stats", {}))
        review_result = ReviewResult(
            pr_url=pr_url,
            summary=result.get("summary", ""),
            risk_level=result.get("risk_level", "LOW"),
            issues=issues,
            stats=stats,
            diff_truncated=result.get("diff_truncated", False),
        )

        event = result.get("event", "")
        diff = result.get("diff", "")
        position_map = _build_position_map(diff) if diff else {}

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                data = await post_review_to_github(
                    owner, repo, pr_number, github_token, review_result, position_map
                )
                if "synchronize" in event:
                    await dismiss_old_reviews(owner, repo, pr_number, github_token)
                return data
            except Exception as e:
                last_exc = e
                if attempt < 2:
                    delay = 2 ** attempt
                    logger.warning(
                        "post_comment attempt %d/3 failed: %s — retrying in %ds",
                        attempt + 1, e, delay,
                    )
                    await asyncio.sleep(delay)

        logger.error(
            "post_comment failed after 3 attempts for %s: %s\n%s",
            pr_url, last_exc, _result_fallback_text(result),
        )
        return None


def _build_position_map(diff: str) -> dict[str, dict[int, int]]:
    from app.services.diff import build_position_map as _bpm
    return _bpm(diff)


def _result_fallback_text(result: dict) -> str:
    issues = result.get("issues", [])
    lines = [
        f"--- fallback review result for {result.get('summary', 'N/A')} ---",
        f"risk_level={result.get('risk_level', 'N/A')}",
        f"issues={len(issues)}",
    ]
    for i, issue in enumerate(issues[:10]):
        sev = issue.get("severity", "?")
        loc = f"{issue.get('file','?')}:{issue.get('line','?')}"
        lines.append(f"  [{i}] {sev} {loc} {issue.get('title','?')}")
    if len(issues) > 10:
        lines.append(f"  ... and {len(issues) - 10} more")
    return "\n".join(lines)


def _risk_level(findings: list[FindingSchema]) -> str:
    for f in findings:
        sev = f.severity if isinstance(f.severity, str) else f.severity.value
        if sev == "ERROR":
            return "HIGH"
    for f in findings:
        sev = f.severity if isinstance(f.severity, str) else f.severity.value
        if sev == "WARNING":
            return "MEDIUM"
    return "LOW"


def _get_stat(context: dict, key: str) -> int:
    stats = context.get("stats")
    if stats is not None and hasattr(stats, key):
        return getattr(stats, key)
    return 0


def _finding_to_dict(f: FindingSchema) -> dict:
    return {
        "file": f.file,
        "line": f.line,
        "title": f.title,
        "description": f.description,
        "severity": f.severity if isinstance(f.severity, str) else f.severity.value,
        "confidence": f.confidence,
        "category": f.category,
        "impact_type": f.impact_type,
        "impact_statement": f.impact_statement,
        "diff_snippet": f.diff_snippet,
        "evidence": f.evidence,
        "token_cost": f.token_cost,
    }


def _verification_findings(verification: dict) -> list[FindingSchema]:
    findings: list[FindingSchema] = []

    imports = verification.get("imports", [])
    if isinstance(imports, list):
        for item in imports:
            if isinstance(item, dict) and item.get("status") == "fail":
                statement = item.get("statement", "")
                module = item.get("module", "")
                findings.append(
                    FindingSchema(
                        file=str(item.get("file", "")),
                        line=item.get("line") if isinstance(item.get("line"), int) else None,
                        title="Unresolved import",
                        description=f"The import `{module}` cannot be resolved. {item.get('detail', '')}".strip(),
                        severity="ERROR",
                        confidence=1.0,
                        category="quality",
                        impact_type="runtime_error",
                        impact_statement=f"Importing {module} fails at build time.",
                        evidence=[statement] if statement else None,
                    )
                )

    exports = verification.get("exports", [])
    if isinstance(exports, list):
        for item in exports:
            if isinstance(item, dict) and item.get("status") == "fail":
                statement = item.get("statement", "")
                symbol = item.get("symbol", "")
                module = item.get("module", "")
                findings.append(
                    FindingSchema(
                        file=str(item.get("file", "")),
                        line=item.get("line") if isinstance(item.get("line"), int) else None,
                        title="Missing named export",
                        description=(
                            f"The symbol `{symbol}` is not exported by `{module}`. "
                            f"{item.get('detail', '')}"
                        ).strip(),
                        severity="ERROR",
                        confidence=1.0,
                        category="quality",
                        impact_type="runtime_error",
                        impact_statement=f"Importing {symbol} from {module} fails at build time.",
                        evidence=[statement] if statement else None,
                    )
                )

    return findings


def _sast_findings(sast: dict) -> list[FindingSchema]:
    findings: list[FindingSchema] = []
    for category in ("security", "quality"):
        for item in sast.get(category, []):
            findings.append(FindingSchema(**item))
    return findings


def split_diff_by_file(diff: str) -> dict[str, str]:
    chunks: dict[str, str] = {}
    current_file: str | None = None
    current_lines: list[str] = []

    for line in diff.split("\n"):
        if line.startswith("diff --git"):
            if current_file is not None and current_lines:
                chunks[current_file] = "\n".join(current_lines)
            current_file = None
            current_lines = [line]
        elif line.startswith("+++ b/") and current_lines is not None:
            current_file = line[6:]
            current_lines.append(line)
        elif current_lines is not None:
            current_lines.append(line)

    if current_file is not None and current_lines:
        chunks[current_file] = "\n".join(current_lines)

    return chunks


def _split_into_batches(context: dict, batch_size: int) -> list[dict]:
    all_files: list[str] = context.get("files", [])
    diff = context.get("diff", "")
    diff_chunks = split_diff_by_file(diff)
    max_tokens = _max_tokens_per_call()

    batches: list[dict] = []
    for i in range(0, len(all_files), batch_size):
        batch_files = all_files[i : i + batch_size]
        batch_diff = "\n".join(
            chunk for f, chunk in diff_chunks.items() if f in batch_files
        )
        for split_diff in _split_diff_by_token_budget(batch_diff, max_tokens):
            batch = {**context, "files": batch_files, "diff": split_diff}
            batches.append(batch)

    return batches


def _estimated_tokens(text: str) -> int:
    return len(text) // _TOKEN_CHARS


def _max_tokens_per_call() -> int:
    from app.config import load_config

    return load_config().review.budget.max_tokens_per_call


def _split_diff_by_token_budget(diff: str, max_tokens: int) -> list[str]:
    if not diff:
        return [""]
    max_chars = max_tokens * _TOKEN_CHARS
    if len(diff) <= max_chars:
        return [diff]

    batches: list[str] = []
    current: list[str] = []
    current_chars = 0
    header: list[str] = []

    for line in diff.splitlines():
        line_chars = len(line) + 1
        if line.startswith("diff --git"):
            header = [line]
        elif line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            header.append(line)

        if current and current_chars + line_chars > max_chars:
            batches.append("\n".join(current))
            current = list(header) if header else []
            current_chars = sum(len(item) + 1 for item in current)

        current.append(line)
        current_chars += line_chars

    if current:
        batches.append("\n".join(current))
    return batches


def _extract_changed_functions(diff: str) -> set[str]:
    # Python: def foo( / async def foo(
    fn_pattern = re.compile(r"^\+\s*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)

    # JS/TS named function — with optional export / export default / async
    # covers: function foo(  /  export function foo(  /  export async function foo(
    js_pattern = re.compile(
        r"^\+\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
        re.MULTILINE,
    )

    # Arrow / const — with optional export
    # covers: const foo = (  /  export const foo = (  /  export const foo = async (
    arrow_pattern = re.compile(
        r"^\+\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\(",
        re.MULTILINE,
    )

    # TypeScript/JS class methods (indented ≥2 spaces, optional access modifier / async)
    # covers: async handleRequest(  /  private validate(  /  public static create(
    method_pattern = re.compile(
        r"^\+\s{2,}(?:(?:public|private|protected|static|override|abstract)\s+)*"
        r"(?:async\s+)?(\w+)\s*\(",
        re.MULTILINE,
    )

    names: set[str] = set()
    for pat in (fn_pattern, js_pattern, arrow_pattern, method_pattern):
        names.update(m.group(1) for m in pat.finditer(diff))
    # 过滤掉明显的非函数名（JS 关键字、单字符）
    _JS_KEYWORDS = {
        "if", "for", "while", "switch", "catch", "return", "throw",
        "new", "delete", "typeof", "void", "await", "yield",
    }
    names -= _JS_KEYWORDS
    names = {n for n in names if len(n) > 1}
    return names


def _changed_node_ids_from_diff(db_path: Path, diff: str) -> set[int]:
    from app.services.diff import build_position_map

    added_lines = {
        file: set(lines.keys())
        for file, lines in build_position_map(diff).items()
        if lines
    }
    if not added_lines:
        return set()

    ids: set[int] = set()
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        for file, lines in added_lines.items():
            for line in sorted(lines):
                rows = conn.execute(
                    """
                    SELECT id
                    FROM nodes
                    WHERE file = ? AND start_line <= ? AND end_line >= ?
                    ORDER BY start_line DESC
                    """,
                    (file, line, line),
                ).fetchall()
                ids.update(row[0] for row in rows)
    finally:
        conn.close()
    return ids


def _format_blast_radius(blast_radius: list[dict]) -> str:
    """Format blast_radius for display/debugging only (no longer used in LLM prompts)."""
    if not blast_radius:
        return ""
    lines = ["## [CROSS-FILE CONTEXT] 调用了被改函数的地方\n"]
    for item in blast_radius:
        lines.append(f"### 被改函数：`{item['changed_fn']}`\n")
        for caller in item["callers"]:
            label = f"{caller['file']}:{caller['start_line']} `{caller['fn']}`"
            lines.append(f"**{label}**")
            lines.append(f"```\n{caller['code']}\n```\n")
    return "\n".join(lines)


def _extract_call_site(caller_code: str, callee_short_name: str, context_lines: int = 5) -> str:
    """Extract a snippet around where callee_short_name is called in caller_code.

    Always includes line 0 (function signature) so the LLM can see default argument
    values like `user_id=None`. For short functions returns the full body.
    """
    # Short functions: return the whole thing — no point truncating.
    if len(caller_code) <= 600:
        return caller_code

    lines = caller_code.splitlines()
    for i, line in enumerate(lines):
        # Match a call: function name followed by ( — avoids matching import/definition lines
        if callee_short_name in line and "(" in line and "def " not in line and "function " not in line:
            # Always anchor at line 0 (function signature) so parameter defaults are visible.
            start = 0
            end = min(len(lines), i + context_lines + 1)
            return "\n".join(lines[start:end])
    # No explicit call site found — return beginning of function for context
    return caller_code[:600]


def _downgrade_severity(severity_str: str) -> str:
    """Cross-file impact findings are one step less severe than the original finding.

    A direct ERROR in a changed function becomes WARNING in a caller (indirect impact).
    """
    order = ["ERROR", "WARNING", "INFO"]
    try:
        idx = order.index(severity_str.upper())
        return order[min(idx + 1, len(order) - 1)]
    except ValueError:
        return "WARNING"

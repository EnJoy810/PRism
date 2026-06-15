import asyncio
import logging
import os
import time
from collections.abc import Sequence

from app.agents.judge import JudgeAgent
from app.agents.performance import PerformanceAgent
from app.agents.quality import QualityAgent
from app.agents.security import SecurityAgent
from app.models.agent import AgentResult, AgentStatus, FindingSchema

logger = logging.getLogger(__name__)

_BATCH_SIZE = 30


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

    async def run(
        self,
        pr_url: str,
        context: dict | None = None,
    ) -> dict:
        t0 = time.monotonic()
        if context is None:
            context = await self.fetch_pr_context(pr_url)
        logger.info("fetch_context done: %s — %.2fs", pr_url, time.monotonic() - t0)

        symbol_task = asyncio.create_task(self._fetch_symbol_context(context, pr_url))
        blast_task = asyncio.create_task(self._fetch_blast_radius(context, pr_url))
        sast_task = asyncio.create_task(self._fetch_sast_findings(context, pr_url))
        verification_task = asyncio.create_task(self._fetch_verification(context, pr_url))

        symbol_defs, blast_radius, sast_findings, verification = await asyncio.gather(
            symbol_task, blast_task, sast_task, verification_task, return_exceptions=True
        )

        context["symbol_definitions"] = symbol_defs if isinstance(symbol_defs, dict) else {}
        context["blast_radius"] = blast_radius if isinstance(blast_radius, list) else []
        context["sast_findings"] = sast_findings if isinstance(sast_findings, dict) else {}
        context["verification"] = verification if isinstance(verification, dict) else {}

        needs_batching = (
            context.get("diff_truncated", False)
            or len(context.get("files", [])) > _BATCH_SIZE
        )
        if not needs_batching:
            return await self._run_single(context, pr_url, t0)

        return await self._run_multi(context, pr_url, t0)

    async def _fetch_symbol_context(self, context: dict, pr_url: str) -> dict[str, str]:
        try:
            from app.services.context import fetch_symbol_context
            from app.services.github import parse_pr_url

            owner, repo, _ = parse_pr_url(pr_url)
            ref = context.get("head_branch", "")
            files = context.get("files", [])
            diff = context.get("diff", "")
            return await fetch_symbol_context(owner, repo, ref, files, diff)
        except Exception as e:
            logger.warning("Symbol context fetch failed: %s", e)
            return {}

    async def _fetch_blast_radius(self, context: dict, pr_url: str) -> list:
        try:
            from app.config import load_config
            from app.services.blast_radius import compute_blast_radius
            from app.services.github import parse_pr_url
            from app.services.indexer import build_index
            from app.services.repo import ensure_repo

            owner, repo, pr_number = parse_pr_url(pr_url)

            head_sha = context.get("head_sha", "")
            if not head_sha:
                logger.debug("no head_sha in context, skip blast radius")
                return []

            cfg = load_config()
            token = cfg.github_token or os.environ.get("GITHUB_TOKEN", "")
            if not token:
                logger.debug("no github token, skip blast radius")
                return []

            repo_path = await ensure_repo(owner, repo, head_sha, token)
            if repo_path is None:
                return []

            db_path = repo_path.parent / f"{repo_path.name}.db"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, build_index, repo_path, db_path)

            changed_fns = _extract_changed_functions(context.get("diff", ""))
            if not changed_fns:
                return []

            diff_tokens = len(context.get("diff", "")) // 4
            result = compute_blast_radius(db_path, changed_fns, diff_tokens)
            logger.info(
                "blast radius: %d changed fns, %d caller groups found",
                len(changed_fns), len(result),
            )
            return result

        except Exception as e:
            logger.warning("blast radius fetch failed: %s", e)
            return []

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
            token = cfg.github_token or os.environ.get("GITHUB_TOKEN", "")
            if not token:
                return {"security": [], "quality": []}

            repo_path = await ensure_repo(owner, repo, head_sha, token)
            if repo_path is None:
                return {"security": [], "quality": []}

            files = context.get("files", [])
            if not files:
                return {"security": [], "quality": []}

            sec, qual = await asyncio.gather(
                run_sast(files, "security", repo_path),
                run_sast(files, "quality", repo_path),
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
            token = cfg.github_token or os.environ.get("GITHUB_TOKEN", "")
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

    async def _run_single(self, context: dict, pr_url: str, t0: float) -> dict:
        diff = context.get("diff", "")
        agent_results = await self._run_agents(diff, context)
        return await self._assemble_result(agent_results, context, pr_url, t0, diff)

    async def _run_multi(self, context: dict, pr_url: str, t0: float) -> dict:
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
            all_agent_results, context, pr_url, t0, context.get("diff", ""),
        )

    async def _run_agents(self, diff: str, context: dict) -> list[AgentResult]:
        blast_radius = context.get("blast_radius", [])
        blast_section = _format_blast_radius(blast_radius)
        sast_findings = context.get("sast_findings", {})

        agent_context = {
            "pr_title": context.get("title", ""),
            "pr_description": context.get("description", ""),
            "files": context.get("files", []),
            "symbol_definitions": context.get("symbol_definitions", {}),
            "blast_radius": blast_radius,
            "blast_radius_section": blast_section,
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
    ) -> dict:
        tj = time.monotonic()
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
        decision: str = judge_output["merge_recommendation"]
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
            "merge_recommendation": decision,
            "skipped_agents": skipped,
        }

    async def post_comment(
        self,
        result: dict,
        pr_url: str,
        github_token: str,
    ) -> dict:
        from app.models.review import ReviewIssue, ReviewResult, ReviewStats
        from app.services.github import parse_pr_url
        from app.services.github_review import post_review_to_github

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
        )

        pr_context = await self.fetch_pr_context(pr_url)
        position_map = _build_position_map(pr_context.get("diff", ""))

        data = await post_review_to_github(
            owner, repo, pr_number, github_token, review_result, position_map
        )
        return data


def _build_position_map(diff: str) -> dict[str, dict[int, int]]:
    from app.services.diff import build_position_map as _bpm
    return _bpm(diff)


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

    batches: list[dict] = []
    for i in range(0, len(all_files), batch_size):
        batch_files = all_files[i : i + batch_size]
        batch_diff = "\n".join(
            chunk for f, chunk in diff_chunks.items() if f in batch_files
        )
        batch = {**context, "files": batch_files, "diff": batch_diff}
        batches.append(batch)

    return batches


def _extract_changed_functions(diff: str) -> set[str]:
    import re
    fn_pattern = re.compile(r"^\+\s*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)
    js_pattern = re.compile(r"^\+\s*(?:async\s+)?function\s+(\w+)\s*\(", re.MULTILINE)
    arrow_pattern = re.compile(r"^\+\s*(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\(", re.MULTILINE)

    names: set[str] = set()
    for pat in (fn_pattern, js_pattern, arrow_pattern):
        names.update(m.group(1) for m in pat.finditer(diff))
    return names


def _format_blast_radius(blast_radius: list[dict]) -> str:
    if not blast_radius:
        return ""
    lines = ["## [CROSS-FILE CONTEXT] 调用了被改函数的地方\n"]
    for item in blast_radius:
        lines.append(f"### 被改函数：`{item['changed_fn']}`\n")
        for caller in item["callers"]:
            lines.append(f"**{caller['file']}:{caller['start_line']}** `{caller['fn']}`")
            lines.append(f"```\n{caller['code']}\n```\n")
    return "\n".join(lines)

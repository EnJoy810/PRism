import asyncio
import logging
import os
import re
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path

from app.agents.judge import JudgeAgent
from app.agents.performance import PerformanceAgent
from app.agents.quality import QualityAgent
from app.agents.security import SecurityAgent
from app.models.agent import AgentResult, AgentStatus, FindingSchema
from app.services.evidence import publication_gate, severity

logger = logging.getLogger(__name__)

_BATCH_SIZE = 30
_TOKEN_CHARS = 4


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

        needs_batching = (
            context.get("diff_truncated", False)
            or len(context.get("files", [])) > _BATCH_SIZE
            or _estimated_tokens(context.get("diff", "")) > _max_tokens_per_call()
        )
        context["_event"] = event
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
            from app.services.blast_radius import compute_blast_radius
            from app.services.github import parse_pr_url
            from app.services.indexer import build_index, ensure_index_schema
            from app.services.repo import ensure_repo

            owner, repo, pr_number = parse_pr_url(pr_url)

            head_sha = context.get("head_sha", "")
            if not head_sha:
                logger.debug("no head_sha in context, skip blast radius")
                return []

            cfg = load_config()
            token = context.get("github_token") or cfg.github_token or os.environ.get("GITHUB_TOKEN", "")
            if not token:
                logger.debug("no github token, skip blast radius")
                return []

            repo_path = await ensure_repo(owner, repo, head_sha, token)
            if repo_path is None:
                return []

            db_path = repo_path.parent / f"{repo_path.name}.db"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, build_index, repo_path, db_path)
            await loop.run_in_executor(None, ensure_index_schema, db_path)

            diff = context.get("diff", "")
            changed_fns = _extract_changed_functions(diff)
            changed_node_ids = _changed_node_ids_from_diff(db_path, diff)
            if not changed_fns and not changed_node_ids:
                return []

            diff_tokens = len(diff) // 4
            result = compute_blast_radius(
                db_path,
                changed_fns,
                diff_tokens,
                changed_node_ids=changed_node_ids,
            )
            logger.info(
                "blast radius: %d changed fns, %d changed nodes, %d caller groups found",
                len(changed_fns), len(changed_node_ids), len(result),
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
    fn_pattern = re.compile(r"^\+\s*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)
    js_pattern = re.compile(r"^\+\s*(?:async\s+)?function\s+(\w+)\s*\(", re.MULTILINE)
    arrow_pattern = re.compile(r"^\+\s*(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\(", re.MULTILINE)

    names: set[str] = set()
    for pat in (fn_pattern, js_pattern, arrow_pattern):
        names.update(m.group(1) for m in pat.finditer(diff))
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
    if not blast_radius:
        return ""
    lines = ["## [CROSS-FILE CONTEXT] 调用了被改函数的地方\n"]
    all_callers: list[str] = []
    for item in blast_radius:
        lines.append(f"### 被改函数：`{item['changed_fn']}`\n")
        for caller in item["callers"]:
            label = f"{caller['file']}:{caller['start_line']} `{caller['fn']}`"
            lines.append(f"**{label}**")
            lines.append(f"```\n{caller['code']}\n```\n")
            all_callers.append(label)
    if all_callers:
        lines.append(
            "\n> **必须逐一检查以下每个调用方是否受到接口变更影响（不能跳过任何一个）：**\n"
            + "\n".join(f"> - {c}" for c in all_callers)
        )
    return "\n".join(lines)

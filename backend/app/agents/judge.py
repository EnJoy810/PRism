import json
import logging

from app.models.agent import AgentResult, AgentStatus, FindingSchema, JudgeVerdict
from app.services.llm import LLMClient

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}

_CATEGORY_KEYWORDS: dict[str, set[str]] = {
    "security": {"password", "credential", "injection", "xss", "csrf", "auth",
                  "permission", "encrypt", "secret", "token", "sql"},
    "performance": {"slow", "latency", "memory", "cache", "timeout", "n+1",
                    "query", "loop", "redundant", "bottleneck", "async"},
    "quality": {"lint", "style", "naming", "format", "duplicate", "dead code",
                "import", "type", "null", "error handling"},
}

_LOW_VALUE_QUALITY_KEYWORDS = {
    "annotation",
    "comment",
    "consistency",
    "docstring",
    "format",
    "formatting",
    "label",
    "naming",
    "readability",
    "style",
    "type annotation",
    "标签",
    "注释",
    "返回注解",
    "格式",
    "可读性",
    "命名",
    "一致性",
    "风格",
}

_CONSEQUENCE_KEYWORDS = {
    "api",
    "backward",
    "break",
    "call",
    "caller",
    "ci",
    "crash",
    "exception",
    "fail",
    "failure",
    "incompatible",
    "mypy",
    "pyright",
    "runtime",
    "signature mismatch",
    "type check",
    "typeerror",
    "兼容",
    "失败",
    "异常",
    "崩溃",
    "破坏",
    "类型检查",
    "签名不匹配",
    "调用",
    "运行时",
}

_LOW_VALUE_IMPACT_TYPES = {"style_only", "info_only", "documentation_only"}

_FRONTEND_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte")

_FRONTEND_PATH_MARKERS = (
    "/components/",
    "/feature/",
    "/hooks/",
    "/pages/",
    "/src/app/",
    "/src/components/",
    "/src/pages/",
)

_FRONTEND_SECURITY_GUESS_KEYWORDS = {
    "auth bypass",
    "authorization bypass",
    "broken access control",
    "idor",
    "insecure direct object reference",
    "server-side request forgery",
    "ssrf",
    "unauthorized access",
    "服务端请求伪造",
    "服务器端请求伪造",
    "权限绕过",
    "越权",
}

_CLIENT_INPUT_KEYWORDS = {
    "client",
    "frontend",
    "id",
    "localstorage",
    "param",
    "query",
    "router",
    "url",
    "window.location",
    "客户端",
    "前端",
    "参数",
}

_SERVER_EVIDENCE_KEYWORDS = {
    "api route",
    "auth check",
    "authorization check",
    "backend",
    "controller",
    "database",
    "middleware",
    "permission check",
    "route handler",
    "server",
}

_PERFORMANCE_MICRO_KEYWORDS = {
    "avoid allocation",
    "could avoid",
    "could be faster",
    "extra render",
    "inline handler",
    "memoize",
    "slightly faster",
    "unnecessary re-render",
    "unnecessary rerender",
    "usecallback",
    "usememo",
    "临时数组",
    "不必要的重新渲染",
    "微优化",
}

_PERFORMANCE_HARD_EVIDENCE_KEYWORDS = {
    "benchmark",
    "deadlock",
    "flamegraph",
    "latency",
    "memory leak",
    "n+1",
    "p95",
    "p99",
    "profile",
    "quadratic",
    "sql query",
    "timeout",
    "unbounded",
}

_ACTIONABLE_IMPACT_TYPES = {
    "api_breakage",
    "behavior_regression",
    "data_loss",
    "performance_regression",
    "resource_leak",
    "runtime_error",
    "security_risk",
    "type_check_failure",
}

_SEMANTIC_DEDUP_PROMPT = """以下是在同一个文件里发现的多个问题摘要。请判断哪些问题是同一个问题（语义重复），只保留其中一个。

返回 JSON 数组，每个元素格式：
{{"keep_index": 0, "duplicate_indices": [1, 2]}}

表示 index 0 被保留，1 和 2 是它的重复。
互不相同的问题各自单独一组：{{"keep_index": 0, "duplicate_indices": []}}

问题列表：
{findings_json}

规则：
- 必须同时满足以下两个条件才能标记为重复：(1) 行号相同或相差 ≤3 行；(2) 描述的是完全相同的现象
- 行号不同的问题，即使类型相似（如都是边界值错误、都是空指针），也不算重复——它们是独立的 bug
- 宁可漏标重复，不可误标不重复"""


def _guess_category(title: str, description: str, current_category: str) -> str | None:
    text = (title + " " + description).lower()
    scores = {cat: sum(1 for kw in kws if kw in text) for cat, kws in _CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] > 0 and best != current_category:
        return best
    return None


def _group_by_file(findings: list[FindingSchema]) -> dict[str, list[FindingSchema]]:
    groups: dict[str, list[FindingSchema]] = {}
    for f in findings:
        groups.setdefault(f.file, []).append(f)
    return groups


def _finding_text(finding: FindingSchema) -> str:
    return " ".join(
        part for part in [
            finding.title,
            finding.description,
            finding.impact_statement or "",
            finding.diff_snippet or "",
            " ".join(finding.evidence or []),
        ]
        if part
    ).lower()


class JudgeAgent:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-v4-pro",
        base_url: str | None = None,
    ):
        self._llm = None
        self._model = model

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient(model=self._model)
        return self._llm

    def dedup(self, findings: list[FindingSchema]) -> list[FindingSchema]:
        # Exact (file, line, title) dedup: same location and same title → keep highest severity.
        # Semantic dedup (LLM-based) handles same-bug-different-title cases downstream.
        by_exact: dict[tuple[str, int | None, str], FindingSchema] = {}
        for f in findings:
            key = (f.file, f.line, f.title)
            existing = by_exact.get(key)
            if existing is None or SEVERITY_ORDER.get(f.severity, 99) < SEVERITY_ORDER.get(existing.severity, 99):
                by_exact[key] = f
        return list(by_exact.values())

    async def _semantic_dedup_group(self, findings: list[FindingSchema]) -> list[FindingSchema]:
        if len(findings) <= 1:
            return findings

        findings_short = [
            {
                "index": i,
                "file": f.file,
                "line": f.line,
                "title": f.title,
                "description": f.description[:100],
                "impact_type": f.impact_type,
            }
            for i, f in enumerate(findings)
        ]

        try:
            content = await self.llm.chat(
                messages=[
                    {"role": "system", "content": "你是一个精准的去重助手，只判断语义重复，不修改问题内容。"},
                    {"role": "user", "content": _SEMANTIC_DEDUP_PROMPT.format(
                        findings_json=json.dumps(findings_short, ensure_ascii=False)
                    )},
                ],
                max_tokens=1024,
                temperature=0.0,
                estimated_tokens=len(findings) * 60,
            )

            raw = content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            # LLM sometimes emits trailing text after the JSON array; extract
            # the first complete [...] block to avoid "Extra data" parse errors.
            bracket = raw.find("[")
            if bracket != -1:
                depth = 0
                for end, ch in enumerate(raw[bracket:], bracket):
                    if ch == "[":
                        depth += 1
                    elif ch == "]":
                        depth -= 1
                        if depth == 0:
                            raw = raw[bracket : end + 1]
                            break
            groups = json.loads(raw)

            keep_indices = {g["keep_index"] for g in groups if isinstance(g, dict) and "keep_index" in g}
            if not keep_indices:
                return findings
            return [f for i, f in enumerate(findings) if i in keep_indices]
        except Exception as e:
            logger.warning("Semantic dedup failed for %d findings: %s", len(findings), e)
            return findings

    def reduce_noise(
        self,
        findings: list[FindingSchema],
        min_confidence: float = 0.6,
    ) -> list[FindingSchema]:
        return [
            f for f in findings
            if f.confidence >= min_confidence and self._has_actionable_impact(f)
        ]

    def decide_merge(self, findings: list[FindingSchema]) -> str:
        for f in findings:
            if f.severity == "ERROR":
                return "REQUEST_CHANGES"
        for f in findings:
            if f.severity == "WARNING":
                return "COMMENT"
        return "APPROVE"

    async def run(
        self,
        results: list[AgentResult],
        min_confidence: float | None = None,
        diff: str | None = None,
        verification: dict | None = None,
    ) -> dict:
        if min_confidence is None:
            from app.config import load_config
            min_confidence = load_config().review.filters.min_confidence
        all_findings: list[FindingSchema] = []

        skipped_agents: list[str] = []
        for i, r in enumerate(results):
            if r.status != AgentStatus.SUCCESS:
                skipped_agents.append(f"agent_{i}")
                continue
            all_findings.extend(r.findings)

        # Pass 1: rule dedup（evidence filter 已移除——行号验证在 publication_gate 里做）
        deduped = self.dedup(all_findings)

        # Pass 2: group by file → semantic dedup per file
        by_file = _group_by_file(deduped)
        semantic_deduped: list[FindingSchema] = []
        for file_path, file_findings in by_file.items():
            grouped = await self._semantic_dedup_group(file_findings)
            semantic_deduped.extend(grouped)

        verified = self._apply_verification(semantic_deduped, verification)
        reclassified = self._reclassify(verified)
        filtered = self.reduce_noise(reclassified, min_confidence)
        gated = self._filter_severity(filtered)
        decision = self.decide_merge(gated)

        return JudgeVerdict(
            findings=gated,
            merge_recommendation=decision,
            skipped_agents=skipped_agents,
        ).model_dump()

    def _filter_severity(
        self,
        findings: list[FindingSchema],
        min_severity: str = "WARNING",
    ) -> list[FindingSchema]:
        order = SEVERITY_ORDER.get(min_severity, 1)
        return [f for f in findings if SEVERITY_ORDER.get(f.severity, 99) <= order]

    def _reclassify(self, findings: list[FindingSchema]) -> list[FindingSchema]:
        result = []
        for f in findings:
            guessed = _guess_category(f.title, f.description, f.category)
            if guessed:
                result.append(f.model_copy(update={"category": guessed}))
            else:
                result.append(f)
        return result

    def _apply_verification(
        self,
        findings: list[FindingSchema],
        verification: dict | None,
    ) -> list[FindingSchema]:
        if not verification:
            return findings

        passed_imports = _passed_verified_imports(verification)
        passed_exports = _passed_verified_exports(verification)
        if not passed_imports and not passed_exports:
            return findings

        return [
            f for f in findings
            if not _is_contradicted_missing_import_finding(f, passed_imports)
            and not _is_contradicted_missing_export_finding(f, passed_exports)
        ]

    def _is_low_value_quality_finding(self, finding: FindingSchema) -> bool:
        if finding.category != "quality" or finding.severity == "ERROR":
            return False

        text = f"{finding.title} {finding.description}".lower()
        has_low_value_marker = any(keyword in text for keyword in _LOW_VALUE_QUALITY_KEYWORDS)
        has_consequence = any(keyword in text for keyword in _CONSEQUENCE_KEYWORDS)
        return has_low_value_marker and not has_consequence

    def _is_frontend_security_guess(self, finding: FindingSchema) -> bool:
        if finding.category != "security":
            return False

        file_path = f"/{finding.file.lower()}"
        is_frontend_file = file_path.endswith(_FRONTEND_EXTENSIONS) or any(
            marker in file_path for marker in _FRONTEND_PATH_MARKERS
        )
        if not is_frontend_file:
            return False

        text = _finding_text(finding)
        return (
            any(keyword in text for keyword in _FRONTEND_SECURITY_GUESS_KEYWORDS)
            and any(keyword in text for keyword in _CLIENT_INPUT_KEYWORDS)
            and not any(keyword in text for keyword in _SERVER_EVIDENCE_KEYWORDS)
        )

    def _is_weak_performance_warning(self, finding: FindingSchema) -> bool:
        if finding.category != "performance" or finding.severity != "WARNING":
            return False

        text = _finding_text(finding)
        has_micro_marker = any(keyword in text for keyword in _PERFORMANCE_MICRO_KEYWORDS)
        has_hard_evidence = any(keyword in text for keyword in _PERFORMANCE_HARD_EVIDENCE_KEYWORDS)
        return has_micro_marker and not has_hard_evidence

    def _has_actionable_impact(self, finding: FindingSchema) -> bool:
        if self._is_frontend_security_guess(finding):
            return False
        if self._is_weak_performance_warning(finding):
            return False

        impact_type = (finding.impact_type or "").strip().lower()
        if impact_type in _LOW_VALUE_IMPACT_TYPES:
            return False
        if impact_type in _ACTIONABLE_IMPACT_TYPES:
            return bool((finding.impact_statement or "").strip())
        return not self._is_low_value_quality_finding(finding)


def _passed_verified_imports(verification: dict) -> set[tuple[str, str]]:
    imports = verification.get("imports", [])
    if not isinstance(imports, list):
        return set()

    passed: set[tuple[str, str]] = set()
    for item in imports:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "pass":
            continue
        file_path = item.get("file")
        module = item.get("module")
        if isinstance(file_path, str) and isinstance(module, str):
            passed.add((file_path, module))
    return passed


def _passed_verified_exports(verification: dict) -> set[tuple[str, str]]:
    exports = verification.get("exports", [])
    if not isinstance(exports, list):
        return set()

    passed: set[tuple[str, str]] = set()
    for item in exports:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "pass":
            continue
        file_path = item.get("file")
        symbol = item.get("symbol")
        if isinstance(file_path, str) and isinstance(symbol, str):
            passed.add((file_path, symbol))
    return passed


def _is_contradicted_missing_import_finding(
    finding: FindingSchema,
    passed_imports: set[tuple[str, str]],
) -> bool:
    text = _finding_text(finding)
    has_missing_import_claim = any(
        keyword in text for keyword in (
            "dependency",
            "import",
            "module",
            "package",
            "cannot resolve",
            "not declared",
            "not found",
            "unresolved",
            "依赖",
            "导入",
            "模块",
            "不存在",
            "未声明",
        )
    )
    if not has_missing_import_claim:
        return False

    return any(
        file_path == finding.file and module in text
        for file_path, module in passed_imports
    )


def _is_contradicted_missing_export_finding(
    finding: FindingSchema,
    passed_exports: set[tuple[str, str]],
) -> bool:
    text = _finding_text(finding)
    has_missing_export_claim = any(
        keyword in text for keyword in (
            "does not export",
            "exported",
            "missing export",
            "not exported",
            "no exported member",
            "no matching export",
            "未导出",
            "没有导出",
        )
    )
    if not has_missing_export_claim:
        return False

    return any(
        file_path == finding.file and symbol.lower() in text
        for file_path, symbol in passed_exports
    )

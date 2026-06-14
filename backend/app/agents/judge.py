import json
import logging

from app.models.agent import AgentResult, AgentStatus, FindingSchema, JudgeVerdict
from app.services.llm import LLMClient

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}
EVIDENCE_REQUIRED = True

_CATEGORY_KEYWORDS: dict[str, set[str]] = {
    "security": {"password", "credential", "injection", "xss", "csrf", "auth",
                  "permission", "encrypt", "secret", "token", "sql"},
    "performance": {"slow", "latency", "memory", "cache", "timeout", "n+1",
                    "query", "loop", "redundant", "bottleneck", "async"},
    "quality": {"lint", "style", "naming", "format", "duplicate", "dead code",
                "import", "type", "null", "error handling"},
}

_SEMANTIC_DEDUP_PROMPT = """以下是在同一个文件里发现的多个问题摘要。请判断哪些问题是同一个问题（语义重复），只保留其中一个。

返回 JSON 数组，每个元素格式：
{{"keep_index": 0, "duplicate_indices": [1, 2]}}

表示 index 0 被保留，1 和 2 是它的重复。
互不相同的问题各自单独一组：{{"keep_index": 0, "duplicate_indices": []}}

问题列表：
{findings_json}

规则：
- 同一行报的多个问题，如果描述的都是同一个现象（如"空指针"和"可能崩溃"是同一个），标记为重复
- 不同行的问题如果描述不同现象，不算重复
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
        seen: dict[tuple[str, int | None, str], FindingSchema] = {}
        for f in findings:
            key = (f.file, f.line, f.title)
            if key in seen:
                existing = seen[key]
                if SEVERITY_ORDER.get(f.severity, 99) < SEVERITY_ORDER.get(existing.severity, 99):
                    seen[key] = f
            else:
                seen[key] = f
        return list(seen.values())

    async def _semantic_dedup_group(self, findings: list[FindingSchema]) -> list[FindingSchema]:
        if len(findings) <= 1:
            return findings

        findings_short = [
            {"index": i, "file": f.file, "line": f.line, "title": f.title, "description": f.description[:100]}
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
                temperature=0.1,
                estimated_tokens=len(findings) * 60,
            )

            raw = content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
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
        return [f for f in findings if f.confidence >= min_confidence]

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

        # Pass 1: evidence filter + rule dedup
        evidenced = self._filter_evidence(all_findings, diff)
        deduped = self.dedup(evidenced)

        # Pass 2: group by file → semantic dedup per file
        by_file = _group_by_file(deduped)
        semantic_deduped: list[FindingSchema] = []
        for file_path, file_findings in by_file.items():
            grouped = await self._semantic_dedup_group(file_findings)
            semantic_deduped.extend(grouped)

        reclassified = self._reclassify(semantic_deduped)
        filtered = self.reduce_noise(reclassified, min_confidence)
        gated = self._filter_severity(filtered)
        decision = self.decide_merge(gated)

        return JudgeVerdict(
            findings=gated,
            merge_recommendation=decision,
            skipped_agents=skipped_agents,
        ).model_dump()

    def _filter_evidence(
        self,
        findings: list[FindingSchema],
        diff: str | None = None,
    ) -> list[FindingSchema]:
        if not EVIDENCE_REQUIRED:
            return findings

        def _evidence_valid(f: FindingSchema) -> bool:
            if not f.evidence or len(f.evidence) == 0:
                return False
            if diff is None:
                return True
            return any(e in diff for e in f.evidence)

        return [f for f in findings if _evidence_valid(f)]

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

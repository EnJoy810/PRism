from app.models.agent import AgentResult, AgentStatus, FindingSchema
from app.services.llm import LLMClient

SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}


class JudgeAgent:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-v4-flash",
        base_url: str | None = None,
    ):
        self.client = LLMClient(api_key=api_key, model=model, base_url=base_url)

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

    def reduce_noise(
        self,
        findings: list[FindingSchema],
        min_confidence: float = 0.6,
    ) -> list[FindingSchema]:
        result = []
        for f in findings:
            if f.confidence < min_confidence:
                current = SEVERITY_ORDER.get(f.severity, 99)
                if current == 0:
                    new_severity = "WARNING"
                elif current == 1:
                    new_severity = "INFO"
                else:
                    new_severity = "INFO"
                result.append(f.model_copy(update={"severity": new_severity}))
            else:
                result.append(f)
        return result

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
        min_confidence: float = 0.6,
    ) -> dict:
        all_findings: list[FindingSchema] = []

        skipped_agents: list[str] = []
        for i, r in enumerate(results):
            if r.status != AgentStatus.SUCCESS:
                skipped_agents.append(f"agent_{i}")
                continue
            all_findings.extend(r.findings)

        deduped = self.dedup(all_findings)
        filtered = self.reduce_noise(deduped, min_confidence)
        decision = self.decide_merge(filtered)

        return {
            "findings": filtered,
            "merge_recommendation": decision,
            "skipped_agents": [],
        }

import json
import re
from abc import ABC, abstractmethod

from json_repair import repair_json

from app.models.agent import AgentResult, AgentStatus, FindingSchema
from app.services.llm import LLMClient


class BaseAgent(ABC):
    category: str
    system_prompt: str

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-v4-flash",
        base_url: str | None = None,
    ):
        self.client = LLMClient(api_key=api_key, model=model, base_url=base_url)
        self.thinking: str = ""

    @abstractmethod
    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        ...

    def _build_messages(self, diff: str, context: dict | None = None) -> list[dict]:
        prompt = self.build_prompt(diff, context)
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]

    def _parse_response(self, content: str) -> tuple[list[FindingSchema], str]:
        thinking = ""
        think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
        if think_match:
            thinking = think_match.group(1).strip()
            json_part = content[think_match.end():].strip()
        else:
            json_part = content.strip()

        repaired = repair_json(json_part, return_objects=False)
        data = json.loads(repaired)
        findings_data = data.get("findings", [])
        findings = [FindingSchema(**f) for f in findings_data]
        return findings, thinking

    async def run(
        self, diff: str, context: dict | None = None
    ) -> AgentResult:
        try:
            messages = self._build_messages(diff, context)
            content = await self.client.chat(
                messages=messages,
                max_tokens=4096,
                temperature=0.7,
                estimated_tokens=len(diff) // 4,
            )

            findings, self.thinking = self._parse_response(content)
            return AgentResult(
                status=AgentStatus.SUCCESS,
                findings=findings,
            )

        except json.JSONDecodeError:
            return AgentResult(
                status=AgentStatus.FORMAT_ERROR,
                findings=[],
                error_message="Failed to parse JSON from LLM response",
            )
        except Exception as e:
            return AgentResult(
                status=AgentStatus.FORMAT_ERROR,
                findings=[],
                error_message=str(e),
            )

import json
import logging
import re
from abc import ABC, abstractmethod

from json_repair import repair_json

from app.models.agent import AgentResult, AgentStatus, FindingSchema
from app.services.llm import LLMClient

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    category: str
    system_prompt: str
    langfuse_prompt_name: str | None = None  # set in subclass to enable remote prompts

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.client = LLMClient(api_key=api_key, model=model, base_url=base_url)
        self.thinking: str = ""
        if self.langfuse_prompt_name:
            from app.services.prompts import get_prompt
            self.system_prompt = get_prompt(self.langfuse_prompt_name, self.__class__.system_prompt)

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

        if "{" in json_part and "}" in json_part:
            json_part = json_part[json_part.find("{"):json_part.rfind("}") + 1]
        repaired = repair_json(json_part, return_objects=False)
        data = json.loads(repaired)
        if isinstance(data, list):
            findings_data = data
        else:
            findings_data = data.get("findings", [])
        findings = []
        for f in findings_data:
            try:
                findings.append(FindingSchema(**f))
            except Exception as e:
                logger.debug("skipping malformed finding: %s — %s", f, e)
        return findings, thinking

    async def run(
        self, diff: str, context: dict | None = None
    ) -> AgentResult:
        try:
            messages = self._build_messages(diff, context)
            content = await self.client.chat(
                messages=messages,
                temperature=0.0,
                estimated_tokens=len(diff) // 4,
            )
        except Exception as e:
            logger.warning("%s: agent failed: %s", self.__class__.__name__, e)
            return AgentResult(
                status=AgentStatus.RUNTIME_ERROR,
                findings=[],
                error_message=str(e),
            )
        try:
            findings, thinking = self._parse_response(content)
            self.thinking = thinking
            return AgentResult(
                status=AgentStatus.SUCCESS,
                findings=findings,
            )
        except Exception as e:
            logger.warning("%s: parse failed: %s", self.__class__.__name__, e)
            return AgentResult(
                status=AgentStatus.FORMAT_ERROR,
                findings=[],
                error_message=str(e),
            )

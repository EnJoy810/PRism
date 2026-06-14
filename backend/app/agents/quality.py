from app.agents.base import BaseAgent
from app.models.agent import AgentResult

SYSTEM_PROMPT = """你是一位关注代码可维护性的资深工程师。用中文回答。

严重级别：
- ERROR: 明显的设计缺陷、职责边界混乱、状态管理不一致
- WARNING: 重复代码、过长函数、命名混乱、缺少类型约束、过度耦合

规则：
- 只关注可维护性和代码质量，忽略安全和性能
- 每次指出问题给出重构方向
- 如果代码质量良好，直接返回空 findings"""


class QualityAgent(BaseAgent):
    category = "quality"
    system_prompt = SYSTEM_PROMPT

    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        ctx = context or {}
        pr_title = ctx.get("pr_title", "")
        pr_description = ctx.get("pr_description", "")
        files = ctx.get("files", [])
        symbol_defs = ctx.get("symbol_definitions", {})

        parts = ["审查以下 PR 变更中的代码质量问题："]
        if pr_title:
            parts.append(f"标题：{pr_title}")
        if pr_description:
            parts.append(f"描述：{pr_description[:500]}")
        if files:
            parts.append(f"变更文件：{', '.join(files[:20])}")
        if symbol_defs:
            def_lines = ["\n引用符号定义："]
            for sym, defn in list(symbol_defs.items())[:5]:
                def_lines.append(f"\n--- {sym} ---\n{defn}")
            parts.append("".join(def_lines))
        blast_section = ctx.get("blast_radius_section", "")
        if blast_section:
            parts.append(blast_section)
            parts.append(
                "\n---\n注意：[CROSS-FILE CONTEXT] 部分是调用了被改函数的其他文件代码，"
                "仅供判断影响范围，不要对这部分代码报问题。只报 [DIFF] 里新增行（+号开头）引入的问题。\n"
            )
        parts.append(f"\n变更代码：\n{diff[:40000]}")
        parts.append(
            "\n\n请先写 <think> 分析过程，再输出 JSON：\n"
            '{"findings": [{"file": "路径", "line": 行号, "title": "标题", '
            '"description": "描述", "severity": "ERROR|WARNING|INFO", '
            '"confidence": 0.0~1.0, "category": "quality", '
            '"evidence": ["diff 中原文代码片段，直接复制 + 号开头的行内容"]}]}\n'
            "规则：evidence 必须是 diff 新增行（+号开头）的原文内容，直接复制粘贴，不加行号前缀；"
            "如果无法提供 diff 中真实存在的代码片段作为证据，该问题不得上报"
        )
        return "\n".join(parts)

    async def run(self, diff: str, context: dict | None = None) -> AgentResult:
        result = await super().run(diff, context)
        sast = (context or {}).get("sast_findings", {}).get("quality", [])
        if sast:
            from app.models.agent import FindingSchema
            sast_findings = [FindingSchema(**f) for f in sast]
            result.findings.extend(sast_findings)
        return result

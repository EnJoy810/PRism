from app.agents.base import BaseAgent

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

        parts = ["审查以下 PR 变更中的代码质量问题："]
        if pr_title:
            parts.append(f"标题：{pr_title}")
        if pr_description:
            parts.append(f"描述：{pr_description[:500]}")
        if files:
            parts.append(f"变更文件：{', '.join(files[:20])}")
        parts.append(f"\n变更代码：\n{diff[:40000]}")
        parts.append(
            "\n\n请先写 <think> 分析过程，再输出 JSON：\n"
            '{"findings": [{"file": "路径", "line": 行号, "title": "标题", '
            '"description": "描述", "severity": "ERROR|WARNING|INFO", '
            '"confidence": 0.0~1.0, "category": "quality"}]}'
        )
        return "\n".join(parts)

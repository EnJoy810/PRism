from app.agents.base import BaseAgent

SYSTEM_PROMPT = """你是一位专注于性能优化的资深工程师。用中文回答。

严重级别：
- ERROR: N+1 查询、内存泄漏、死锁、大对象重复创建、同步阻塞 IO
- WARNING: 不必要的循环、缓存缺失、懒加载缺失、批量操作可优化

规则：
- 只关注性能相关的问题，忽略安全和风格
- 提供数据量级估算（如：1000 次请求时，这个循环会…）
- 如果未发现性能问题，直接返回空 findings"""


class PerformanceAgent(BaseAgent):
    category = "performance"
    system_prompt = SYSTEM_PROMPT

    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        ctx = context or {}
        pr_title = ctx.get("pr_title", "")
        pr_description = ctx.get("pr_description", "")
        files = ctx.get("files", [])

        parts = ["审查以下 PR 变更中的性能风险："]
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
            '"confidence": 0.0~1.0, "category": "performance"}]}'
        )
        return "\n".join(parts)

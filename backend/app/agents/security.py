from app.agents.base import BaseAgent

SYSTEM_PROMPT = """你是一位专注于安全审计的资深工程师。用中文回答。

严重级别：
- ERROR: SQL 注入、XSS、CSRF、敏感信息泄露、认证授权缺陷、命令注入
- WARNING: 输入验证不足、HTTPS 缺失、权限控制不严、不安全随机数

规则：
- 只关注安全相关的问题，忽略风格和性能
- 每个问题提供具体的攻击场景和修复方法
- 如果未发现安全问题，直接返回空 findings"""


class SecurityAgent(BaseAgent):
    category = "security"
    system_prompt = SYSTEM_PROMPT

    def build_prompt(self, diff: str, context: dict | None = None) -> str:
        ctx = context or {}
        pr_title = ctx.get("pr_title", "")
        pr_description = ctx.get("pr_description", "")
        files = ctx.get("files", [])

        parts = ["审查以下 PR 变更中的安全风险："]
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
            '"confidence": 0.0~1.0, "category": "security"}]}'
        )
        return "\n".join(parts)

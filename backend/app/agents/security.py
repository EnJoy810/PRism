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
        symbol_defs = ctx.get("symbol_definitions", {})

        parts = ["审查以下 PR 变更中的安全风险："]
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
            '"confidence": 0.0~1.0, "category": "security", '
            '"impact_type": "security_risk|info_only", '
            '"impact_statement": "具体攻击路径或数据泄露后果", '
            '"evidence": ["diff 中原文代码片段，直接复制 + 号开头的行内容"]}]}\n'
            "规则：evidence 必须是 diff 新增行（+号开头）的原文内容，直接复制粘贴，不加行号前缀；"
            "impact_type 必须描述实际后果；只有安全风险用 security_risk，"
            "安全最佳实践建议用 info_only；impact_statement 必须是可验证后果，不能只写可能/也许；"
            "如果无法提供 diff 中真实存在的代码片段作为证据，该问题不得上报"
        )
        return "\n".join(parts)

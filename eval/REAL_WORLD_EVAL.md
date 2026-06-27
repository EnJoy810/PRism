# 真实 PR 评测方案

## 指标

**精确率（Precision）= TP / (TP + FP)**

- TP（真阳性）：finding 指出的问题确实存在于代码中
- FP（误报）：finding 指出的问题不存在、是正常写法、或与 diff 无关
- 目标：**>= 70%**

## 执行标准

### 什么算 TP

满足以下任一即为 TP：
1. **代码证据存在**：finding 引用的行号在 diff 的 + 行中确实存在，且该行代码确实存在 finding 描述的问题
2. **开发者确认**：finding 贴到 PR 后，开发者回复承认问题存在（或默默修复）
3. **逻辑可验证**：即使开发者不回复，通过阅读 diff 可以确认问题描述准确

### 什么算 FP

满足以下任一即为 FP：
1. **行号不存在**：finding 引用的行号不在 diff 的 + 行中
2. **正常写法被误判**：代码是合理的实现，finding 把正常模式当问题
3. **与 diff 无关**：finding 讨论的是删除行（- 行）或未变更的代码
4. **重复问题**：同一问题被不同 Agent 重复报出（Judge 未去重）

### 不计入分母

以下 finding 不计入 precision 计算：
- INFO 级别（已默认过滤）
- evidence 为空的 finding（已由 publication_gate 过滤）
- 明显的工具错误（如 LLM 输出格式错误导致的解析失败）

## 执行流程

### Phase 1：跑 Review（今天）

从以下仓库各选 2 个 PR（共 10 个）：
- encode/httpx
- sphinx-doc/sphinx
- scikit-learn/scikit-learn
- django/django
- pallets/flask

选择标准：
- 最近 2 周创建的 open PR
- 有实际代码变更（排除 dependabot/docs/CI bump）
- 变更量 10-200 行（排除超大 PR）
- 优先选有逻辑变更的，优先排除纯类型注解/文档修正

### Phase 2：分类（跑完后）

对每个 finding：
1. 人工验证代码证据是否存在
2. 如果无法确定，标记为 "需要开发者确认"
3. 计算 precision = TP / (TP + FP)

### Phase 3：发到 GitHub（可选）

从 precision > 70% 的结果中，挑 3-5 条最有价值的 finding，手动贴到对应 PR 的评论区，观察开发者反应（48 小时内）。

## 记录格式

每个 PR 的结果记录在 `eval/records/real-world/YYYY-MM-DD-<repo>-<pr>.md`：

```markdown
# <repo>#<pr> — <title>

## Meta
- 变更量: +X/-Y, Z files
- 运行时间: Xs

## Findings

| # | Sev | File:Line | Title | Verdict | Evidence |
|---|-----|-----------|-------|---------|----------|
| 1 | WARNING | foo.py:42 | ... | TP/FP/NEEDS_CONFIRM | ... |

## Precision
- TP: X
- FP: Y
- NEEDS_CONFIRM: Z
- Precision: X/(X+Y) = XX%

## Notes
...
```

## 验收

- 10 个 PR 全部跑完
- 每个 finding 有 TP/FP/NEEDS_CONFIRM 分类
- 总体 precision >= 70%

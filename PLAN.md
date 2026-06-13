# 开发计划

> 基于 ARCH.md 的实现顺序。每个 PR 做一件事，符合竞赛规范。

---

## PR 1 — 基础设施

改动范围：新增 Redis 队列 + 配置文件 + LLM Client 容错。不涉及 Agent 逻辑。

- [ ] 新增 `pyproject.toml` 依赖：`arq[redis]`、`langgraph`、`langsmith`
- [ ] 新增 `app/config.py`：读取 `prism.yaml` 和 `DEEPSEEK_API_KEY`
- [ ] 重构 `app/services/llm.py`：抽离 LLM Client，加重试逻辑、token 预算预检、实时消耗追踪
- [ ] 新增 `app/services/queue.py`：ARQ Worker + Redis 连接
- [ ] 新增 `app/routers/webhook.py`：GitHub App Webhook 入口，HMAC 签名验证，入队
- [ ] 更新 `app/main.py`：注册 webhook router 和 Redis 生命周期
- [ ] 新增 `prism.yaml` 配置文件，示例包含 budget/agent/filters/skip
- [ ] 更新 `docker-compose.yml`：加 Redis + Worker 服务
- [ ] 单元测试：LLM Client 重试策略、配置文件读取、签名验证

**验证方式**：
```
curl -X POST http://localhost:8000/api/webhook \
  -H "X-GitHub-Event: pull_request" \
  -H "X-Hub-Signature-256: sha256=..."
  -d '{"action": "opened", ...}'
# 预期：返回 202，Redis 队列有任务
```

---

## PR 2 — Agent 接口定义 + 专家 Agent

改动范围：定义 Agent 基类和三个专家 Agent 的实现。每个 Agent 可独立运行。

- [ ] 新增 `app/models/agent.py`：
  - `FindingSchema`：file, line, title, description, severity, confidence, category, diff_snippet
  - `AgentResult`：findings list + status（success / timeout / format_error）
  - `JudgeVerdict`：confirmed findings + dropped reasons + merge_recommendation
- [ ] 新增 `app/agents/base.py`：
  - `BaseAgent` 抽象类：`async def run(diff, context) → AgentResult`
  - 两阶段提示：先 `<think>` 自由推理 → 再提取结构化 JSON
  - 出口 Pydantic 校验，格式异常返回 `AgentResult(status="format_error")`
- [ ] 新增 `app/agents/security.py`：安全审查 Agent
- [ ] 新增 `app/agents/performance.py`：性能审查 Agent
- [ ] 新增 `app/agents/quality.py`：代码规范 Agent
- [ ] 单元测试：每个 Agent 用模拟 diff 测试输出格式、空发现场景、格式异常降级

**验证方式**：
```python
agent = SecurityAgent()
result = await agent.run(diff=test_diff, context={})
assert result.status == "success"
assert all(f.category == "security" for f in result.findings)
```

---

## PR 3 — 裁判 Agent

改动范围：裁判 Agent + 去重/降噪/合并规则。

- [ ] 新增 `app/agents/judge.py`：
  - 去重：同一文件同一行相同标题 → 保留最高 severity
  - 再分类：走错分区的问题挪回正确分区
  - 降噪：confidence < 阈值 → 降一级
  - 合并建议：根据最终 issue 优先级确定 APPROVE / REQUEST_CHANGES / COMMENT
  - 标注跳过：任何 Agent `status != "success"` 时，在摘要标注"XX Agent 本次未返回"
- [ ] `judge.py` 内规则全部确定性实现（同文件同行同标题去重、阈值过滤等）
- [ ] 裁判 LLM 调用仅用于：汇总摘要、risk_level 判断
- [ ] 单元测试：去重规则、降噪阈值、空输入、部分 Agent 缺失

**验证方式**：
```python
judge = JudgeAgent()
result = await judge.run(findings=[
    FindingSchema(file="a.ts", line=10, title="bug", severity="ERROR"),
    FindingSchema(file="a.ts", line=10, title="bug", severity="ERROR"),  # 重复
])
assert len(result.findings) == 1  # 去重
```

---

## PR 4 — LangGraph 图 + 管道串联

改动范围：将 Agent 编排成图，串联完整流程。

- [ ] 新增 `app/graph.py`：
  - `fetch_context` node
  - 三个专家 Agent 并行 fan-out
  - `judge` node
  - `post_comment` node
  - 图编译，不加 checkpoint（不需要）
- [ ] `fetch_context` 超长 PR 多轮次逻辑：分批次塞入 context
- [ ] 重写 `app/routers/review.py`：
  - `/api/review` 调用完整图，返回 ReviewResult
  - `/api/review/stream` SSE 推送裁判 thinking + result
- [ ] 集成测试：用 mock GitHub API 跑通完整图

**验证方式**：
```python
result = await graph.ainvoke({"pr_url": "..."})
assert result.summary
assert len(result.issues) >= 0
```

---

## PR 5 — GitHub App Webhook 自动触发

改动范围：PR 打开/同步时自动触发审查，写回评论区。

- [ ] `app/routers/webhook.py`：完善 Webhook 事件处理
  - `pull_request opened/synchronize` → 入队审查
  - `issue_comment` 含 `@prism-bot` → 入队追加上下文
- [ ] `post_comment` 节点：调用 GitHub Review API 写回评论区
  - 重试 + 落盘补发
- [ ] Webhook 签名验证硬实现（不依赖第三方库）
- [ ] 更新 `README.md`：GitHub App 注册指南

**验证方式**：
打开一个真实 GitHub PR，查看评论区自动出现审查结果。

---

## PR 6 — 工程扫尾

改动范围：可观测性、CI、文档。

- [ ] LangSmith tracing 接入（free tier）
- [ ] 结构化日志：每节点开始/结束、耗时、token 数
- [ ] docker-compose 最终验证：`docker compose up` 一键启动
- [ ] 更新 ARCH.md、CLAUDE.md、README.md
- [ ] 所有 pytest 通过 + ruff 无告警

---

## PR 依赖关系

```
PR 1（基础设施） → PR 2（Agent） → PR 4（图编排）
                  ↗
PR 1（基础设施） → PR 3（裁判）  → PR 4（图编排）
                                    ↘
                                  PR 5（Webhook）→ PR 6（工程扫尾）
```

PR 2 和 PR 3 无依赖关系，可并行开发。
PR 5 和 PR 6 无依赖关系，可并行开发。

每个 PR 保持主分支可运行。PR 合并后删除对应功能分支。

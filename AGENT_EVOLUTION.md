# PRism Agent 演进规划

> 沉淀自 2026-06-12 与 AI 的设计对话。  
> 目标：把 PRism 从"Web 工具"演进成"住在 GitHub 里的 AI Review Agent"。

---

## 背景与方向

### 面试官反馈

> "这种项目形态别做成 Web 端的，而是类似 CodeRabbit 那种，光 @ 就能自己跑的。"

**核心差距：**

| 现在的 PRism | 目标形态 |
|------------|---------|
| 用户打开网页 → 粘贴 PR 链接 → 点按钮 → 看结果 | PR 开了 → Agent 自动触发 → 在 PR 评论区 review → @bot 追问 → 继续回复 |
| 被动工具 | 主动 Agent |
| 单次 LLM 调用 | LangGraph 多步推理 |
| 无状态 | Checkpoint 持久化，支持多轮对话 |

### 为什么不直接参考 kodus-ai / openreview

**openreview**（vercel-labs/openreview，1,358 ★）：架构思路值得参考，但核心依赖不可用：
- `DurableAgent`：Vercel 内部包 `@workflow/ai/agent`，未开源
- `e2b sandbox`：每次 review 启动隔离容器跑 `gh` CLI，PRism 不需要执行任意 shell，直接调 GitHub REST API 即可

**kodus-ai**（kodustech/kodus-ai，1,072 ★）：enterprise monorepo，4 个 app + 20 个 shared libs，Webhook/Agent 逻辑埋得很深，参考成本远大于收益。

**结论**：参考 openreview 的架构思路，用 PRism 已有技术栈（FastAPI + httpx + Python）重新实现，不照搬任何代码。

---

## 行业最佳实践

来源：[Multi-Agent PR Review with LangGraph](https://medium.com/@anilnishad19799/multi-agent-pr-review-system-a9408fe287a9) + [CodeRabbit on Cloud Run](https://cloud.google.com/blog/products/ai-machine-learning/how-coderabbit-built-its-ai-code-review-agent-with-google-cloud-run)

### 核心架构模式

```
Webhook 触发
    ↓
立刻返回 202（GitHub 要求 10 秒内响应）
    ↓
后台 Worker 异步跑 LangGraph pipeline
    ↓
三个 Agent 并行执行
├── Agent 1：代码质量（命名/DRY/错误处理）
├── Agent 2：安全漏洞（注入/硬编码密钥/鉴权）
└── Agent 3：性能问题（N+1/复杂度/阻塞IO）
    ↓
Final Agent：汇总三家结论，格式化 Markdown
    ↓
GitHub API 写回 PR 评论
```

### 关键设计决策

| 决策 | 原因 |
|------|------|
| 立刻返回 202 + 后台异步 | GitHub Webhook 10 秒超时限制 |
| 三个专家 Agent 而非一个 generalist | 专注 system prompt 准确率更高，相关性更强 |
| 并行而非串行 | 3 × 10s 串行 = 30s；并行 = 10s（瓶颈为最慢的 Agent） |
| LangGraph Checkpoint | 持久化对话状态，@bot 追问时接续上下文 |
| `thread_id = repo#pr_number` | 每个 PR 独立对话链路 |

### CodeRabbit 有但 PRism 不需要的

- **沙箱执行**（e2b / Cloud Run microVM）：CodeRabbit 需要跑 linter/formatter/LLM 生成的 shell 脚本，PRism 只调 GitHub REST API，不需要
- **企业级基础设施**：Cloud Tasks 队列、200 并发实例。FastAPI `BackgroundTasks` → Redis + ARQ 够用

---

## 现有代码资产盘点

PRism 已有的东西比想象中完整，演进是**重组而非重写**：

| 文件 | 现有能力 | 复用方式 |
|------|---------|---------|
| `services/github.py` | `fetch_pr_context`：拉 diff + 文件列表 + 文件内容 | 直接作为 LangGraph `fetch_context` 节点 |
| `services/github_review.py` | `post_review_to_github`：写回 PR review | 作为 `final` 节点的 tool |
| `services/llm.py` | `stream_analyze_pr`：SSE 流式 LLM 调用 | 改造为各 Agent 节点的 LLM 调用基础 |
| `routers/review.py` | `/review/stream`：SSE 端点 | Web 端保留，Dashboard 用 |

**缺的只有三块**：GitHub App Webhook 触发、LangGraph 多 Agent 编排、异步队列。

---

## 三阶段演进规划

### Phase 1 — GitHub App 接入（预计 1-2 天）

**目标**：PR 开了自动触发 review，结果出现在 PR 评论区。

新增文件：
```
backend/app/routers/webhook.py      ← Webhook 入口 + HMAC 验证
backend/app/services/github_app.py  ← GitHub App 认证（Octokit 等价）
```

核心逻辑：

```python
# webhook.py
@router.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    verify_signature(await request.body(), request.headers["X-Hub-Signature-256"])

    payload = await request.json()
    event = request.headers.get("X-GitHub-Event")

    if event == "pull_request" and payload["action"] in ("opened", "synchronize"):
        background_tasks.add_task(run_agent_review, payload)

    if event == "issue_comment" and "@prism-bot" in payload["comment"]["body"]:
        background_tasks.add_task(run_agent_followup, payload)

    return Response(status_code=202)
```

**不需要 Redis**：FastAPI `BackgroundTasks` 先顶上，Phase 2 再换。

---

### Phase 2 — LangGraph 多 Agent（预计 2-3 天）

**目标**：从单次 LLM 调用变成真正的 Agent pipeline，支持 @bot 追问对话。

新增文件：
```
backend/app/agents/
    graph.py        ← LangGraph 主图 + Checkpointer
    quality.py      ← 代码质量 Agent
    security.py     ← 安全漏洞 Agent
    performance.py  ← 性能 Agent
    reviewer.py     ← Final 汇总 Agent
```

**State 设计**：

```python
class ReviewState(TypedDict):
    # 输入
    owner: str
    repo: str
    pr_number: int
    thread_id: str              # repo#pr_number，追问时接续上下文

    # fetch_context 产出
    diff: str
    files: list[str]

    # 三个并行 Agent 产出（Annotated 防止并发写冲突）
    quality_issues:     Annotated[list, operator.add]
    security_issues:    Annotated[list, operator.add]
    performance_issues: Annotated[list, operator.add]

    # final 产出
    final_comment: str
```

**图结构**：

```python
graph.add_edge(START, "fetch_context")
# 并行分叉
graph.add_edge("fetch_context", "quality")
graph.add_edge("fetch_context", "security")
graph.add_edge("fetch_context", "performance")
# 汇合
graph.add_edge("quality",      "final")
graph.add_edge("security",     "final")
graph.add_edge("performance",  "final")
graph.add_edge("final", END)

checkpointer = AsyncSqliteSaver.from_conn_string("prism.db")
graph.compile(checkpointer=checkpointer)
```

**持久化对话**：

```python
# 第一次触发（PR opened）
await graph.ainvoke(
    {"messages": [...]},
    config={"configurable": {"thread_id": "owner/repo#123"}}
)

# 有人 @bot 追问，同一 thread_id 自动接续历史
await graph.ainvoke(
    {"messages": [{"role": "user", "content": "@prism-bot 第42行为什么有问题？"}]},
    config={"configurable": {"thread_id": "owner/repo#123"}}
)
```

---

### Phase 3 — Web Dashboard 升级（预计 1-2 天）

**目标**：Web 端从"主功能"变成"配置面板 + 历史记录"，与 GitHub bot 互补。

新增页面：

| 路由 | 内容 |
|------|------|
| `/dashboard` | 所有 bot review 的历史记录 |
| `/settings` | 配置 review 规则（跳过文件、severity 阈值、自定义 checklist） |
| `/pr/:id` | 单个 PR 的 review 详情 + **Agent 推理过程可视化** |

**Agent 推理过程可视化**是最大差异化点：用户能实时看到三个 Agent 分别在想什么，thinking token 流式展示。这在 CollabDoc 里已有 SSE 经验可直接迁移。

---

## 面试 Demo 路径

```
1. 打开一个 GitHub PR
2. 展示 @prism-bot 自动出现在评论区的 review 结果
3. 在评论区 @prism-bot 追问某个具体问题
4. 切到 Web Dashboard 看该 PR 的 Agent 推理过程（三个 Agent 并行思考可视化）
5. 讲 LangGraph 状态机设计
6. 讲为什么三个 Agent 并行而不是一个 generalist
7. 讲 Checkpoint 怎么实现追问的上下文连续性
8. 讲 202 + BackgroundTasks 为什么是必须的设计
```

每一个决策都有"因为 X 所以 Y"的工程理由，所有代码都是自己写的，面试官追问任何细节都能接住。

---

## 技术栈总结

| 层 | 技术 | 说明 |
|----|------|------|
| Webhook 入口 | FastAPI（已有） | 加 HMAC 签名验证路由 |
| 异步队列 | FastAPI BackgroundTasks → Redis + ARQ | Phase 1 用前者，Phase 2 升级 |
| Agent 编排 | LangGraph | 多节点并行 + Checkpoint |
| 状态持久化 | SQLite Checkpointer（开发）/ PostgreSQL（生产） | 支持 @bot 追问 |
| GitHub 集成 | GitHub REST API via httpx（已有） | 拉 diff、写评论、写 review |
| 可观测性 | LangSmith 免费 tier | 调试 Agent 行为 |
| 流式展示 | SSE（已有）| thinking token 可视化 |

# PRism 架构设计

> 当前事实源：GitHub App + FastAPI + ARQ Worker + 多 Agent ReviewGraph。前端已废弃，审查结果 UI 是 GitHub PR 页面。

---

## 产品边界

PRism 做一件事：在 GitHub PR 打开或同步时自动审查代码，并把少量高置信度问题写回 PR 评论区。

不做的事：

- 不维护独立 Review Dashboard
- 不把整仓库塞给 LLM
- 不用向量 RAG 追调用关系
- 不承诺覆盖动态调用
- 不支持 GitLab / Bitbucket 等多平台

---

## 系统架构

```text
GitHub PR event
  opened / synchronized / issue_comment @prism-bot
        |
        v
FastAPI webhook
  - HMAC signature verification
  - GitHub App event parsing
  - return 202 quickly
        |
        v
Redis / ARQ queue
        |
        v
Worker
        |
        v
ReviewGraph
  - fetch PR diff and metadata
  - prepare optional SAST and cross-file context
  - run Security / Quality / Performance agents in parallel
  - rule dedupe
  - Judge semantic grouping and severity calibration
  - evidence validation
        |
        v
GitHub Review API
  - inline comments
  - summary comment
```

### 核心模块

| 模块 | 职责 | 约束 |
|------|------|------|
| `app/main.py` | FastAPI app 入口 | 只注册路由和生命周期 |
| `app/routers/webhook.py` | GitHub webhook 入口 | 验签后入队，不直接跑 review |
| `app/worker.py` | ARQ worker | 消费队列并调用 ReviewGraph |
| `app/graph.py` | ReviewGraph 编排 | router 不直接编排 Agent |
| `app/auth.py` | GitHub App JWT / installation token | token 不写日志 |
| `app/services/github.py` | 获取 PR diff / metadata | router 不直接调用 httpx |
| `app/services/github_review.py` | 写回 PR 评论 | GitHub API 重试和格式转换 |
| `app/services/llm.py` | OpenAI-compatible LLM 调用 | 所有模型调用都走这里 |
| `app/agents/*` | 专家 Agent 和 Judge | 输出 Pydantic schema |
| `app/services/sast.py` | Semgrep wrapper | 不可用时静默降级 |
| `app/services/repo.py` | shallow clone + cache | clone `head.sha`，不是默认分支 |
| `app/services/indexer.py` | tree-sitter -> SQLite | 单文件失败不影响主链路 |
| `app/services/blast_radius.py` | BFS 查调用方 | depth=2，token 预算受控 |

---

## ReviewGraph 流程

```text
input: owner, repo, pr_number, installation_id/token
        |
        v
fetch_context
  - PR diff
  - PR title / description
  - changed files
  - head sha
        |
        +------------------------------+
        |                              |
        v                              v
optional context pipeline          expert agents
  - Semgrep SAST                    - SecurityAgent
  - shallow clone                   - QualityAgent
  - tree-sitter index               - PerformanceAgent
  - blast radius
        |                              |
        +---------------+--------------+
                        v
rule dedupe
        |
        v
JudgeAgent
  - semantic grouping
  - severity calibration
  - INFO filtering
        |
        v
evidence validation
  - line/snippet must exist in diff added lines
        |
        v
post GitHub comments
```

并行策略：短期使用 `asyncio.gather`，不引入 LangGraph checkpoint。只有当后续需要复杂分支、恢复、长期对话状态时再评估 LangGraph。

---

## Agent 设计

### 专家 Agent

| Agent | 关注范围 | 不关注 |
|-------|----------|--------|
| Security | 注入、鉴权、敏感信息、输入校验、安全配置 | 风格、性能 |
| Quality | 设计缺陷、边界条件、可维护性、重复逻辑 | 纯格式问题 |
| Performance | N+1、阻塞 IO、重复计算、内存/复杂度问题 | 安全、命名 |

每个 Agent 必须输出结构化 JSON，由 `FindingSchema` 校验。格式异常时该 Agent 降级为空结果，不中断整次审查。

### Judge Agent

Judge 不是重新审查代码，而是处理候选 findings：

1. 规则去重：同文件、同行、同标题的显式重复先合并。
2. 按文件分组：减少 Judge 单次输入 token。
3. 语义分组：处理表达不同但本质相同的问题。
4. Severity gating：默认过滤 INFO，只保留 WARNING / ERROR。
5. 合并输出：生成 summary comment 和 inline comment 数据。

---

## 上下文策略

原则：少而精，避免注意力稀释。

| 层级 | 内容 | 设计理由 |
|------|------|----------|
| Diff | PR 新增/修改行 | finding 只能报 diff 引入的问题 |
| Metadata | 标题、描述、文件列表 | 帮助理解改动意图 |
| Symbol context | 符号定义/短片段 | 比整文件上下文更可控 |
| Blast radius | 调用方函数片段 | 发现跨文件影响，但不扩大报错范围 |
| SAST findings | Semgrep 结果 | 确定性问题不完全依赖 LLM |

关键约束：

- Prompt 必须标注 `[DIFF]` 和 `[CONTEXT]`。
- Agent 只能对 `[DIFF]` 中新增行报问题。
- `[CONTEXT]` 只用于判断影响范围，不作为直接评论对象。
- 调用图失败、clone 失败、Semgrep 不存在时都降级为 diff-only。

---

## 调用图设计

### 数据流

```text
PR head.sha
   |
   v
repo.py shallow clone
   |
   v
indexer.py parse Python / JS / TS with tree-sitter
   |
   v
SQLite nodes + edges
   |
   v
blast_radius.py BFS callers depth=2
   |
   v
agent context [CROSS-FILE CONTEXT]
```

### 工程约束

- clone 使用 PR 的 `head.sha`，避免用默认分支最新代码审老 PR。
- 按 `repo@sha` 隔离缓存和 SQLite，防并发写冲突。
- 跳过 `node_modules/`、`vendor/`、`dist/`、`test_*.py`、`*.test.ts`。
- 单文件解析失败只跳过该文件。
- BFS 默认 `depth=2`，并用 diff token 的 50% 作为上下文预算上限。
- installation token 不出现在日志。

### 已知边界

- Python `getattr`、JS Proxy 等动态调用无法静态追踪。
- 行为语义变化无法仅靠调用图可靠识别。
- 跨语言调用暂不支持。
- 超大仓库 clone 超时后降级，不阻塞主链路。

---

## 幻觉控制

核心规则：没有 evidence 的 finding 不能发出去。

### Evidence 验证

LLM 输出必须包含：

- 文件路径
- 行号
- 代码片段 evidence
- severity
- description
- confidence

程序验证：

- 行号必须落在 diff 新增行范围内。
- evidence 片段必须能在 diff 新增行中找到。
- 引用变量或函数名必须真实出现在对应片段中。

LLM confidence 只作为辅助信号，不作为唯一过滤机制。

---

## SAST 集成

`services/sast.py` 统一封装 Semgrep：

- Security rules: `p/security-audit`、`p/owasp-top-ten`
- Quality rules: `p/python`、`p/javascript`、`p/typescript`
- Semgrep 不存在、文件不存在、扫描失败时返回空列表
- SAST findings 合并进 Agent result，再交给 Judge 去重和 severity gating

当前定位：增强信号，不是主链路依赖。

---

## 配置与预算

配置来源：`app/config.py` + `prism.yaml` + 环境变量。LLM 使用 OpenAI-compatible 接口，`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 优先于旧版 `DEEPSEEK_API_KEY`。

关键预算：

- 单次模型上下文不超过配置的 `max_tokens_per_call`
- 总上下文目标上限 16K
- blast radius 上下文不超过 diff token 估算的 50%
- Agent 超时或异常时跳过该 Agent，不整次失败

---

## 部署

生产形态：Docker Compose 或服务器上的等价进程管理。

```text
api     FastAPI webhook / health check
worker  ARQ Worker
redis   queue backend
```

本地验证：

```bash
cd backend
uvicorn app.main:app --reload --port 8000
python -m app.worker
python -m app.cli review https://github.com/owner/repo/pull/42
```

---

## 可观测性

- `graph.py` 输出各阶段耗时、token、finding 数量。
- `LANGSMITH_TRACING=true` 时追踪 LLM 调用。
- Worker 日志记录降级原因，但不记录 token、私钥、clone URL 中的 installation token。

---

## 当前技术债

- README、CLAUDE、ARCH 已统一当前事实；历史文档仍保留演进过程。
- 调用图模块已存在，但需要真实仓库评测来证明收益。
- SAST wrapper 已存在，但 Semgrep 环境依赖和 rule 配置仍需部署验证。
- BlockDiff 仍是规划，尚未进入主链路。

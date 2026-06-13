# PRism — CLAUDE.md

> AI-powered PR Review Assistant. Backend: FastAPI + Python 3.12. Frontend: React 18 + Vite + TypeScript.

## 项目结构

- `frontend/` — React SPA，负责 PR URL 输入、Review 结果展示
- `backend/` — FastAPI，负责 GitHub 数据获取 + DeepSeek LLM 分析

## 启动命令

```bash
# 后端（API 服务）
cd backend && uvicorn app.main:app --reload --port 8000

# 后端（Worker — 消费 Webhook 审查队列）
cd backend && python -m app.worker

# Docker 一键启动（API + Worker + Redis）
docker compose up --build

# 前端
cd frontend && pnpm dev
```

## 核心约束

### 后端
- 所有 LLM 调用走 `app/services/llm.py`，不在 router 层直接调用 openai SDK
- Severity Gating 在 `JudgeAgent` 内执行，INFO 级别默认过滤
- GitHub 数据获取走 `app/services/github.py`，router 层不直接调用 httpx
- 编排走 `app/graph.py`（ReviewGraph），不直接在 router 层编排 Agent
- Webhook 队列消费走 `app/worker.py`（ARQ），不直接用 BackgroundTasks

### 前端
- 请求层统一走 `src/utils/request.ts`
- 布局/间距 → Tailwind；交互组件 → Ant Design token
- 禁止行内 style
- 状态管理：TanStack Query 管服务端数据，Zustand 管 UI 状态

### 通用
- 禁止 `--no-verify`
- commit 格式：`<type>(<scope>): <描述>`

## 构建验证

```bash
# 后端
.venv/bin/ruff check app/ tests/ && .venv/bin/python -m pytest tests/ -v

# 前端（若脚本存在）
cd frontend && pnpm lint && pnpm typecheck
```

## AI 全量编码质量契约

### 原则

不要把 AI 写的代码当真，直到有客观证据证明它对。

### 规则 1：写测试先于写实现（TDD with AI Agents）

```
Red（写失败测试）→ 你确认测试正确 → Green（最小实现让它通过）→ 你确认 AI 没偷改测试 → Refactor
```

- 每步开工前我会问：主人，这步先写测试还是先实现？
- 我写测试（Red）后你先审，测试通过了你签字，我再写实现（Green）
- **严禁 AI 在 Green 阶段修改测试代码**。如果实现需要通过改测试来变绿，说明合约（测试）错了，你重订合约
- Refactor 阶段不改行为，只改质量（lint/type/命名/抽取）

### 规则 2：七层质量门

| 层 | 捕获什么 | PRism 具体工具 | 谁执行 |
|----|---------|---------------|--------|
| 1. Lint | 风格漂移、死代码、幻觉 import | `ruff check app/ tests/` | AI |
| 2. Type Check | 类型漂移、`any` 回退 | `mypy app/ --strict`（若安装） | AI |
| 3. 安全扫描 | 硬编码密钥、SQL 注入 | 无 SAST 工具时不强推 | — |
| 4. 测试覆盖 | 新代码未覆盖、回归 | `pytest tests/ -v --cov=app/` | AI |
| 5. 边界一致 | 跨模块接口不匹配 | 编译时由类型系统保证 | 自动 |
| 6. 对抗 LLM 审查 | 幻觉 API、遗漏边缘情况、过度工程 | 你换一个模型（Claude 或其他）审我 diff | 你 |
| 7. 最终签字 | 业务逻辑正确性 | 你看 diff，确认 AI 没改测试、没偷跑 | 你 |

每层只管前一层漏掉的东西。第 7 层你砍掉可以，但前 6 层我跑。

**门禁**：PR 合并前必须跑通第 1 + 第 4 层。若第 2 层工具（mypy）不存在则跳过。

### 规则 3：AI 改过的文件一律视为未测试

场景：我改了 `llm.py` → 为了编译通过改了 `main.py` 的 import → 顺手改了 `test_llm.py` 的 mock。

规则：
- 我不修改任何测试文件，除非你明确要求我修（且此时你需要重审测试）
- 我改过的文件，相关测试全部重跑
- 你在 diff 里确认我没有偷改测试来匹配实现

### 规则 4：Builder 和 Validator 隔离

我写代码（Builder），你审或者用不同模型审我输出（Validator）。

执行方式：
- 我不审自己的代码
- 每个 PR 的 diff，你换一个模型（Claude 或其他）扫一遍，专门找：幻觉 API、遗漏的边缘情况、过度工程
- 审出来的问题归入 PR 的 issues，不改好不合入

### 规则 5：每 PR 是独立可验证单元

PLAN.md 的 6 个 PR 已按此拆分，每 PR 符合：
- **改 ≤3 个核心文件**（例外：纯新增配置/测试不计入）
- **独立可验证**：有测试或手动验证方式
- **不改测试**：除非 PR 本身是"改测试"
- **主分支可运行**：PR 合入后 `uvicorn app.main:app --reload` 能启动

### 仲裁机制

我违反以上任何规则时，你：
1. 说"规则 X 违反"
2. 我立即停止当前操作
3. 你给出修正方向，我照做

## 架构决策

- **模型**：deepseek-v4-pro（1M context，OpenAI 兼容接口）
- **上下文策略**：PR diff + metadata + 文件列表（Level 2），后续扩展调用链分析（Level 3）
- **误报控制**：Severity Gating — INFO 默认不报，规则驱动而非 LLM 判断严重程度
- **流式输出**：`/api/review/stream` 走 SSE，`/api/review` 走标准 JSON
- **编排**：asyncio.gather 并行执行（短期），后续评估 LangGraph
- **可观测性**：LangSmith tracing + 结构化日志（graph.py 各阶段计时）

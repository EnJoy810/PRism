# PRism — CLAUDE.md

> AI-powered PR Review Assistant. Backend: FastAPI + Python 3.12. Frontend: React 18 + Vite + TypeScript.

## 项目结构

- `frontend/` — React SPA，负责 PR URL 输入、Review 结果展示
- `backend/` — FastAPI，负责 GitHub 数据获取 + Claude LLM 分析

## 启动命令

```bash
# 后端
cd backend && uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && pnpm dev
```

## 核心约束

### 后端 [P0]
- 所有 LLM 调用走 `app/services/llm.py`，不在 router 层直接调用 anthropic SDK
- Severity Gating 在 `analyze_pr()` 内执行，INFO 级别默认过滤
- GitHub 数据获取走 `app/services/github.py`，router 层不直接调用 httpx

### 前端 [P0]
- 请求层统一走 `src/utils/request.ts`
- 布局/间距 → Tailwind；交互组件 → Ant Design token
- 禁止行内 style
- 状态管理：TanStack Query 管服务端数据，Zustand 管 UI 状态

### 通用 [P0]
- 禁止 `--no-verify`
- commit 格式：`<type>(<scope>): <描述>`

## 架构决策

- **模型**：claude-opus-4-5（代码理解能力最强，200k context）
- **上下文策略**：PR diff + metadata + 文件列表（Level 2），后续扩展调用链分析（Level 3）
- **误报控制**：Severity Gating — INFO 默认不报，规则驱动而非 LLM 判断严重程度
- **流式输出**：`/api/review/stream` 走 SSE，`/api/review` 走标准 JSON

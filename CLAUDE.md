# PRism — CLAUDE.md

> AI-powered PR Review Assistant. Backend: FastAPI + Python 3.12. Frontend: React 18 + Vite + TypeScript.

## 项目结构

- `frontend/` — React SPA，负责 PR URL 输入、Review 结果展示
- `backend/` — FastAPI，负责 GitHub 数据获取 + DeepSeek LLM 分析

## 启动命令

```bash
# 后端
cd backend && uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && pnpm dev
```

---

## 竞赛规范 [P0 — 违反视为无效作品]

> 来源：七牛云 × XEngineer 暑期实训营第二批次评审规则（5月29日 – 5月31日）

### 提交有效性

- **持续提交**：所有 commit 时间戳必须落在 5月29日 00:00 – 5月31日 23:59 之内
- **严禁突击**：禁止在最后一天一次性导入所有代码，否则直接视为无效
- **每个 PR 只做一件事**：单一功能/单一模块，大功能必须拆分为多个小 PR 分步提交
- **鼓励小粒度 PR**：粒度越细越好，体现持续开发过程

### PR 规范（每个 PR 必须包含以下四项）

```
① 标题：一句话说明本 PR 新增/修改了什么
② 功能描述：说明该功能的作用与使用方式
③ 实现思路：简要说明技术选型或核心实现逻辑
④ 测试方式：如何验证该功能正常运行
```

- PR 描述不得为空，且必须与实际代码变更相符
- 引用第三方库必须在 README 依赖列表中列明，并说明原创功能部分
- 复用自己过去的代码片段必须在 PR 描述中注明来源

### 主分支可运行性

- PR 合并后主分支代码必须保持可运行状态
- 评委在任意时间查看应能复现演示效果

### 仓库可见性

- 5月31日 23:59 前：可设为私有（防抄袭）
- 6月1日 00:00 起：必须设为公开（供评委评审）

---

## 核心约束

### 后端 [P0]
- 所有 LLM 调用走 `app/services/llm.py`，不在 router 层直接调用 openai SDK
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

---

## 架构决策

- **模型**：deepseek-v4-pro（1M context，OpenAI 兼容接口）
- **上下文策略**：PR diff + metadata + 文件列表（Level 2），后续扩展调用链分析（Level 3）
- **误报控制**：Severity Gating — INFO 默认不报，规则驱动而非 LLM 判断严重程度
- **流式输出**：`/api/review/stream` 走 SSE，`/api/review` 走标准 JSON

<div align="center">
  <h1>🔷 PRism</h1>
  <p><strong>AI 驱动的 Pull Request 代码审查助手</strong></p>
  <p>将 PR 折射为可执行的洞察 — 由 Claude Opus 驱动</p>

  <p>
    <img src="https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react" />
    <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi" />
    <img src="https://img.shields.io/badge/Claude-Opus_4.5-D97757?style=flat-square" />
    <img src="https://img.shields.io/badge/TypeScript-strict-3178C6?style=flat-square&logo=typescript" />
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" />
  </p>
</div>

---

## ✨ 项目简介

PRism 是一款 AI 辅助代码审查工具，基于 Claude Opus 4.5 分析 GitHub Pull Request。粘贴 PR 链接，几秒内获得结构化、可操作的 Review 反馈 — 精准的严重程度分级，极低的误报率。

> 参赛作品：七牛云 × XEngineer 暑期实训营 2026。

---

## 🎯 核心功能

| 功能 | 描述 |
|------|------|
| **智能上下文获取** | 不止拉取 diff，还获取 PR 元数据、commit 信息和文件上下文 |
| **严重程度分级门控** | 确定性三级分类（ERROR / WARNING / INFO），INFO 默认过滤 |
| **流式 Review 输出** | SSE 实时流式传输，边分析边展示 |
| **误报控制** | System prompt 强制 85%+ 置信度阈值；样式问题需手动开启 |
| **风险评估** | PR 整体风险等级（HIGH / MEDIUM / LOW）一目了然 |

---

## 🏗 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                         PRism                               │
│                                                             │
│  ┌──────────────┐    REST/SSE    ┌───────────────────────┐  │
│  │   React SPA  │◄─────────────►│   FastAPI 后端        │  │
│  │              │               │                       │  │
│  │  • URL 输入  │               │  ┌─────────────────┐  │  │
│  │  • 流式渲染  │               │  │  GitHub Service  │  │  │
│  │  • 问题卡片  │               │  │  • PR diff       │  │  │
│  │              │               │  │  • 元数据        │  │  │
│  └──────────────┘               │  │  • 文件上下文    │  │  │
│                                 │  └────────┬────────┘  │  │
│                                 │           │           │  │
│                                 │  ┌────────▼────────┐  │  │
│                                 │  │   LLM Service   │  │  │
│                                 │  │  • ReAct prompt │  │  │
│                                 │  │  • 严重度门控   │  │  │
│                                 │  │  • Claude Opus  │  │  │
│                                 │  └─────────────────┘  │  │
│                                 └───────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 环境要求

- Node.js 20+ 和 pnpm
- Python 3.12+
- [Anthropic API Key](https://console.anthropic.com/)
- GitHub Personal Access Token（可选，提升 API 速率限制）

### 1. 克隆项目

```bash
git clone https://github.com/EnJoy810/PRism.git
cd PRism
```

### 2. 启动后端

```bash
cd backend
cp .env.example .env
# 在 .env 中填写 ANTHROPIC_API_KEY

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. 启动前端

```bash
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev
```

打开 [http://localhost:5173](http://localhost:5173)，粘贴任意公开 GitHub PR 链接即可开始。

---

## 🔌 API 文档

### `POST /api/review`

分析 PR 并返回结构化 JSON Review 结果。

**请求体：**
```json
{
  "pr_url": "https://github.com/owner/repo/pull/123",
  "github_token": "ghp_...",
  "options": {
    "include_style": false
  }
}
```

**响应：**
```json
{
  "code": "0",
  "data": {
    "summary": "本 PR 新增了鉴权中间件，整体质量中等。",
    "risk_level": "MEDIUM",
    "issues": [
      {
        "severity": "ERROR",
        "file": "src/auth.ts",
        "line": 42,
        "title": "潜在的空指针引用",
        "description": "session 过期时 user.token 可能为 undefined",
        "suggestion": "访问 user.token 前添加空值检查"
      }
    ],
    "stats": { "files_changed": 3, "additions": 120, "deletions": 45 }
  }
}
```

### `POST /api/review/stream`

请求体相同，返回 SSE 流式输出，支持实时渲染。

---

## 🛠 技术栈

**前端**
- React 18 + Vite 7 + TypeScript（strict 模式）
- Ant Design 5 + Tailwind CSS 3
- TanStack Query 5 + Zustand 5
- MSW 开发环境 Mock

**后端**
- FastAPI 0.115 + Python 3.12
- Anthropic SDK（Claude Opus 4.5）
- httpx 异步调用 GitHub API
- Pydantic v2 数据校验

---

## 🧠 设计决策

### 为什么选择 Claude Opus 4.5？

Claude Opus 4.5 拥有 200k token 上下文窗口，在真实代码审查任务上优于 GPT-4o — 更擅长解释细微 bug、处理多文件重构。超大上下文窗口意味着即便面对大型 PR 也几乎无需截断。

### 为什么用确定性门控而不是让 LLM 判断严重程度？

LLM 自行分配严重级别不可靠 — 模型倾向于过度上报警告。PRism 使用确定性门控：只有当模型能给出具体代码位置和可操作建议时，该问题才通过 ERROR/WARNING 阈值。INFO 级别默认过滤，可通过 `include_style: true` 手动开启。

### 上下文获取策略

| 层级 | 获取内容 | 现状 |
|------|---------|------|
| L1 | 仅 PR diff | 大多数工具 |
| L2 | diff + 元数据 + 文件列表 | PRism（当前） |
| L3 | L2 + GitHub GraphQL 调用链分析 | PRism（规划中） |

---

## 📍 后续规划

- [ ] 通过 GitHub GraphQL 获取调用链上下文（Level 3）
- [ ] PR 历史学习 — 识别仓库内的重复模式
- [ ] GitHub Actions 集成，支持 CI 自动 Review
- [ ] 团队规则自定义（`.prism.yml` 配置文件）

---

## 📄 开源协议

MIT © 2026 enjoy810

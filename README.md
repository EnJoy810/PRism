<div align="center">
  <h1>🔷 PRism</h1>
  <p><strong>AI-Powered Pull Request Review Assistant</strong></p>
  <p>Refract your PRs into actionable insights — powered by Claude Opus</p>

  <p>
    <img src="https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react" />
    <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi" />
    <img src="https://img.shields.io/badge/Claude-Opus_4.5-D97757?style=flat-square" />
    <img src="https://img.shields.io/badge/TypeScript-strict-3178C6?style=flat-square&logo=typescript" />
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" />
  </p>
</div>

---

## ✨ What is PRism?

PRism is an AI-assisted code review tool that analyzes GitHub Pull Requests using Claude Opus 4.5. Paste a PR URL, get structured, actionable feedback in seconds — with precise severity classification and minimal noise.

> Built for the Qiniu Cloud × XEngineer Summer Training Camp 2026.

---

## 🎯 Key Features

| Feature | Description |
|---------|-------------|
| **Smart Context Fetching** | Pulls PR diff, metadata, commit messages, and file context — not just the diff |
| **Severity Gating** | Deterministic three-tier classification (ERROR / WARNING / INFO) with INFO filtered by default |
| **Streaming Reviews** | Real-time SSE streaming so you see results as Claude thinks |
| **False Positive Control** | 85%+ confidence threshold enforced via system prompt; style issues opt-in only |
| **Risk Assessment** | Overall PR risk level (HIGH / MEDIUM / LOW) at a glance |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         PRism                               │
│                                                             │
│  ┌──────────────┐    REST/SSE    ┌───────────────────────┐  │
│  │   React SPA  │◄─────────────►│   FastAPI Backend     │  │
│  │              │               │                       │  │
│  │  • URL Input │               │  ┌─────────────────┐  │  │
│  │  • Streaming │               │  │  GitHub Service  │  │  │
│  │    Renderer  │               │  │  • PR diff       │  │  │
│  │  • Issue     │               │  │  • Metadata      │  │  │
│  │    Cards     │               │  │  • File context  │  │  │
│  └──────────────┘               │  └────────┬────────┘  │  │
│                                 │           │           │  │
│                                 │  ┌────────▼────────┐  │  │
│                                 │  │   LLM Service   │  │  │
│                                 │  │  • ReAct prompt │  │  │
│                                 │  │  • Severity gate│  │  │
│                                 │  │  • Claude Opus  │  │  │
│                                 │  └─────────────────┘  │  │
│                                 └───────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Node.js 20+ and pnpm
- Python 3.12+
- [Anthropic API key](https://console.anthropic.com/)
- GitHub Personal Access Token (optional, increases rate limits)

### 1. Clone & Install

```bash
git clone https://github.com/enjoy810/PRism.git
cd PRism
```

### 2. Backend

```bash
cd backend
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
pnpm install
cp .env.example .env.local
pnpm dev
```

Open [http://localhost:5173](http://localhost:5173) and paste any public GitHub PR URL.

---

## 🔌 API Reference

### `POST /api/review`

Analyze a PR and return structured JSON review.

```json
{
  "pr_url": "https://github.com/owner/repo/pull/123",
  "github_token": "ghp_...",
  "options": {
    "include_style": false
  }
}
```

**Response:**
```json
{
  "code": "0",
  "data": {
    "summary": "...",
    "risk_level": "MEDIUM",
    "issues": [
      {
        "severity": "ERROR",
        "file": "src/auth.ts",
        "line": 42,
        "title": "Potential null dereference",
        "description": "...",
        "suggestion": "..."
      }
    ],
    "stats": { "files_changed": 3, "additions": 120, "deletions": 45 }
  }
}
```

### `POST /api/review/stream`

Same request body, returns SSE stream for real-time rendering.

---

## 🛠 Tech Stack

**Frontend**
- React 18 + Vite 7 + TypeScript (strict mode)
- Ant Design 5 + Tailwind CSS 3
- TanStack Query 5 + Zustand 5
- MSW for development mocking

**Backend**
- FastAPI 0.115 + Python 3.12
- Anthropic SDK (Claude Opus 4.5)
- httpx for async GitHub API calls
- Pydantic v2 for schema validation

---

## 🧠 Design Decisions

### Why Claude Opus 4.5?

Claude Opus 4.5 has a 200k token context window and outperforms GPT-4o on real-world code review tasks — better at explaining subtle bugs and handling multi-file refactors. The large context window means we rarely need to truncate large PRs.

### Why Severity Gating Instead of LLM Classification?

LLM-assigned severity is unreliable — models tend to over-report warnings. PRism uses a deterministic gate: only issues where the model provides a concrete code location and specific suggestion pass the ERROR/WARNING threshold. INFO issues are filtered by default (opt-in via `include_style: true`).

### Context Fetching Strategy

| Level | What we fetch | Who does this |
|-------|--------------|---------------|
| L1 | PR diff only | Most tools |
| L2 | diff + metadata + file list | PRism (current) |
| L3 | L2 + call-site analysis via GraphQL | PRism (roadmap) |

---

## 📍 Roadmap

- [ ] Call-site context via GitHub GraphQL (Level 3 context)
- [ ] PR history learning — detect repeated patterns in a repo
- [ ] GitHub Actions integration for automated CI review
- [ ] Team rule customization (`.prism.yml` config)

---

## 📄 License

MIT © 2026 enjoy810

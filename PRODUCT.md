# PRism — Product Context（历史记录）

> 状态说明：本文记录早期 Web 产品语境。当前产品形态已调整为 GitHub App + CLI，无独立前端；审查结果 UI 是 GitHub PR 页面。当前事实源以 `CLAUDE.md`、`ARCH.md`、`README.md` 为准。

## Product Purpose
AI-powered GitHub PR Review assistant. Developer pastes a PR URL, gets structured, streamed code review feedback in seconds — with severity classification (ERROR / WARNING / INFO), risk level, and actionable suggestions.

## Users
Individual developers and small teams who want fast, low-noise automated code review before merging. Primary user: developer reviewing their own or a teammate's PR. Context: seated at desk, focused, wants signal not noise.

## Register
product

## Brand Tone
Precise, direct, tool-native. No marketing fluff. Confidence without arrogance. The tool should feel like a sharp senior engineer, not a chatbot.

## Anti-references
- Gradient-heavy SaaS dashboards (Vercel, Linear aesthetic overused)
- Neon-on-black "hacker" aesthetic
- Overly rounded, pastel "friendly AI" (ChatGPT, Claude UI)
- GitHub Copilot (too corporate grey)

## Strategic Principles
1. The streaming output IS the hero moment — design must make AI thinking visible and compelling
2. Severity classification must be scannable in 2 seconds
3. Empty state should invite action, not decorate
4. No chrome that doesn't serve the task

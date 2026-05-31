import type { ReviewResult, PRMeta } from '../../types/review'

export function parseDiffToMap(lines: string[]): Map<string, string[]> {
  const map = new Map<string, string[]>()
  let currentFile: string | null = null
  let currentLines: string[] = []
  for (const line of lines) {
    const m = line.match(/^diff --git a\/.+ b\/(.+)$/)
    if (m) {
      if (currentFile) map.set(currentFile, currentLines)
      currentFile = m[1]
      currentLines = []
    } else if (currentFile) {
      currentLines.push(line)
    }
  }
  if (currentFile) map.set(currentFile, currentLines)
  return map
}

export function buildMarkdown(result: ReviewResult, prUrl: string, meta: PRMeta | null): string {
  const lines: string[] = []
  lines.push(`# PR Review: ${meta?.pr_title ?? prUrl}`)
  lines.push(`\n> ${prUrl}\n`)
  lines.push(`## 摘要\n\n${result.summary}\n`)

  if (result.risk_areas && result.risk_areas.length > 0) {
    lines.push(`## 风险分析\n`)
    for (const r of result.risk_areas) {
      lines.push(`- **[${r.level}]** \`${r.file}\` — ${r.title}: ${r.impact}`)
    }
    lines.push('')
  }

  if (result.issues.length > 0) {
    lines.push(`## 审查发现\n`)
    for (const issue of result.issues) {
      lines.push(`### [${issue.severity}] ${issue.title}`)
      lines.push(`**文件**: \`${issue.file}\`${issue.line ? ` · 第 ${issue.line} 行` : ''}`)
      lines.push(`\n${issue.description}`)
      if (issue.suggestion) lines.push(`\n**建议**: ${issue.suggestion}`)
      if (issue.diff_snippet) lines.push(`\n\`\`\`diff\n${issue.diff_snippet}\n\`\`\``)
      lines.push('')
    }
  }

  if (result.merge_recommendation) {
    const rec = result.merge_recommendation
    lines.push(`## 合并建议\n`)
    lines.push(`**决策**: ${rec.decision} (置信度 ${rec.confidence}%)\n`)
    for (const r of rec.reasons) lines.push(`- ${r}`)
    lines.push('')
  }

  lines.push(`---\n*由 PRism AI 生成*`)
  return lines.join('\n')
}

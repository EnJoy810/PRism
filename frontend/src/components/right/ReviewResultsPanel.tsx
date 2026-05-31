import { useState, useRef } from 'react'
import type { PRMeta, ReviewResult, ReviewIssue, Severity, RiskArea, MergeRecommendation } from '../../types/review'
import { useSettings } from '../../stores/reviewOptions'
import SettingsDrawer from '../common/SettingsDrawer'

interface Props {
  prUrl: string | null
  meta: PRMeta | null
  githubToken?: string
  onDiffLoaded?: (diffMap: Map<string, string[]>) => void
}

type FilterTab = 'all' | Severity

// ─── Style constants ───────────────────────────────────────────────────────────

const CARD_STYLE: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #E5E7EB',
  borderRadius: 10,
  overflow: 'hidden',
  flexShrink: 0,
}

const CARD_HEADER_STYLE: React.CSSProperties = {
  padding: '10px 16px',
  borderBottom: '1px solid #F1F5F9',
  fontWeight: 700,
  fontSize: 13,
  color: '#0F172A',
  display: 'flex',
  alignItems: 'center',
  gap: 8,
}

const CARD_BODY_STYLE: React.CSSProperties = {
  padding: '12px 16px',
}

const SEV_LABEL: Record<Severity, string> = { ERROR: 'Critical', WARNING: 'Warning', INFO: 'Suggestion' }
const SEV_COLOR: Record<Severity, { bg: string; text: string }> = {
  ERROR:   { bg: '#EF4444', text: '#fff' },
  WARNING: { bg: '#F59E0B', text: '#fff' },
  INFO:    { bg: '#3B82F6', text: '#fff' },
}

const RISK_CONFIG: Record<string, { bg: string; text: string; border: string; label: string }> = {
  HIGH:   { bg: '#FEF2F2', text: '#DC2626', border: '#FECACA', label: '高风险' },
  MEDIUM: { bg: '#FFFBEB', text: '#D97706', border: '#FDE68A', label: '中等风险' },
  LOW:    { bg: '#ECFDF5', text: '#059669', border: '#A7F3D0', label: '低风险' },
}

const DECISION_CONFIG: Record<string, { bg: string; text: string; border: string; label: string }> = {
  APPROVE:         { bg: '#ECFDF5', text: '#059669', border: '#A7F3D0', label: 'APPROVE' },
  REQUEST_CHANGES: { bg: '#FEF2F2', text: '#DC2626', border: '#FECACA', label: 'REQUEST CHANGES' },
  COMMENT:         { bg: '#FFFBEB', text: '#D97706', border: '#FDE68A', label: 'COMMENT' },
}

const btnStyle: React.CSSProperties = {
  height: 30,
  padding: '0 12px',
  borderRadius: 6,
  border: '1px solid #E5E7EB',
  background: '#fff',
  color: '#374151',
  fontSize: 12,
  fontWeight: 500,
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  gap: 5,
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function DiffBlock({ snippet }: { snippet: string }) {
  return (
    <div
      style={{
        background: '#0D1117',
        borderRadius: 6,
        overflow: 'hidden',
        fontSize: 12,
        fontFamily: "'JetBrains Mono', Consolas, monospace",
        marginBottom: 10,
      }}
    >
      {snippet.split('\n').map((line, i) => {
        const isAdd = line.startsWith('+')
        const isDel = line.startsWith('-')
        return (
          <div
            key={i}
            style={{
              display: 'flex',
              background: isAdd ? 'rgba(46,160,67,0.15)' : isDel ? 'rgba(248,81,73,0.15)' : 'transparent',
              padding: '1px 12px',
            }}
          >
            <span style={{ color: isAdd ? '#3FB950' : isDel ? '#F85149' : '#8B949E', minWidth: 14 }}>
              {isAdd ? '+' : isDel ? '-' : ' '}
            </span>
            <span style={{ color: '#E6EDF3', paddingLeft: 8 }}>{line.slice(isAdd || isDel ? 1 : 0)}</span>
          </div>
        )
      })}
    </div>
  )
}

function IssueRow({
  issue,
  expanded,
  onToggle,
}: {
  issue: ReviewIssue
  expanded: boolean
  onToggle: () => void
}) {
  const sev = SEV_COLOR[issue.severity]
  return (
    <div style={{ borderBottom: '1px solid #F1F5F9' }}>
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 16px',
          background: expanded ? '#F8FAFF' : 'transparent',
          cursor: 'pointer',
          transition: 'background 0.1s',
        }}
        onClick={onToggle}
        onMouseEnter={e => { if (!expanded) (e.currentTarget as HTMLDivElement).style.background = '#F8FAFC' }}
        onMouseLeave={e => { if (!expanded) (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
      >
        <span
          style={{
            background: sev.bg, color: sev.text,
            fontSize: 10, fontWeight: 700,
            padding: '2px 7px', borderRadius: 4,
            letterSpacing: '0.04em', flexShrink: 0,
          }}
        >
          {SEV_LABEL[issue.severity]}
        </span>
        <span
          style={{
            fontSize: 11, color: '#64748B',
            fontFamily: "'JetBrains Mono', Consolas, monospace",
            flexShrink: 0, maxWidth: 200,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {issue.file}{issue.line ? ` · ${issue.line}L` : ''}
        </span>
        <span style={{ fontSize: 13, color: '#0F172A', fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {issue.title}
        </span>
        <button
          onClick={e => { e.stopPropagation(); navigator.clipboard.writeText(`${issue.file}: ${issue.title}`) }}
          style={{ background: 'none', border: '1px solid #E5E7EB', borderRadius: 5, cursor: 'pointer', padding: '3px 8px', fontSize: 11, color: '#64748B', flexShrink: 0 }}
        >
          复制
        </button>
        <svg
          width="14" height="14" viewBox="0 0 24 24" fill="#94A3B8"
          style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s', flexShrink: 0 }}
        >
          <path d="M7 10l5 5 5-5z"/>
        </svg>
      </div>

      {expanded && (
        <div style={{ padding: '0 16px 16px', background: '#F8FAFF' }}>
          {issue.diff_snippet && <DiffBlock snippet={issue.diff_snippet} />}
          <p style={{ fontSize: 13, color: '#374151', marginBottom: 8, lineHeight: 1.6 }}>{issue.description}</p>
          {issue.suggestion && (
            <div
              style={{
                background: '#F0FDF4', border: '1px solid #BBF7D0',
                borderRadius: 6, padding: '8px 12px', fontSize: 12,
                color: '#166534', marginBottom: 12,
              }}
            >
              <strong>建议：</strong>{issue.suggestion}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function parseDiffToMap(lines: string[]): Map<string, string[]> {
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

// ─── Card components ───────────────────────────────────────────────────────────

function ThinkingPanel({
  thinkText,
  streaming,
  thinkDone,
  thinkCollapsed,
  setThinkCollapsed,
  thinkRef,
}: {
  thinkText: string
  streaming: boolean
  thinkDone: boolean
  thinkCollapsed: boolean
  setThinkCollapsed: (v: boolean | ((prev: boolean) => boolean)) => void
  thinkRef: React.RefObject<HTMLDivElement>
}) {
  return (
    <div style={{ ...CARD_STYLE }}>
      <button
        onClick={() => setThinkCollapsed(c => !c)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 16px', background: '#FAFAFA',
          border: 'none', cursor: 'pointer', textAlign: 'left',
          borderBottom: thinkCollapsed ? 'none' : '1px solid #F1F5F9',
        }}
      >
        {streaming && !thinkDone ? (
          <span style={{
            width: 7, height: 7, borderRadius: '50%',
            background: '#8B5CF6', display: 'inline-block',
            animation: 'pulse 1.2s ease-in-out infinite', flexShrink: 0,
          }} />
        ) : (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="#8B5CF6"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
        )}
        <span style={{ fontSize: 12, fontWeight: 700, color: '#6D28D9', flex: 1 }}>
          {streaming && !thinkDone ? 'AI 正在思考…' : '查看思考过程'}
        </span>
        <svg
          width="13" height="13" viewBox="0 0 24 24" fill="#94A3B8"
          style={{ transform: thinkCollapsed ? 'rotate(-90deg)' : 'none', transition: 'transform 0.2s', flexShrink: 0 }}
        >
          <path d="M7 10l5 5 5-5z"/>
        </svg>
      </button>

      {!thinkCollapsed && (
        <div
          ref={thinkRef}
          style={{
            maxHeight: 160, overflowY: 'auto',
            padding: '10px 14px',
            background: '#FAFAFA',
            fontSize: 12, color: '#6B7280',
            fontStyle: 'italic', lineHeight: 1.7,
            whiteSpace: 'pre-wrap',
          }}
        >
          {thinkText}
          {streaming && !thinkDone && (
            <span style={{
              display: 'inline-block', width: 2, height: '1em',
              background: '#8B5CF6', verticalAlign: 'text-bottom',
              animation: 'pulse 0.8s ease-in-out infinite',
            }} />
          )}
        </div>
      )}
    </div>
  )
}

function AISummaryCard({ result, meta }: { result: ReviewResult; meta: PRMeta | null }) {
  const readingTime = meta ? Math.max(1, Math.round((meta.files_changed ?? 0) / 2)) : 1
  const priorityFiles = result.priority_files ?? []

  return (
    <div style={CARD_STYLE}>
      <div style={CARD_HEADER_STYLE}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#2563EB"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm-1 7V3.5L18.5 9H13zM6 20V4h5v7h7v9H6z"/></svg>
        AI 摘要
        <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 400, color: '#94A3B8' }}>
          预计阅读 ~{readingTime} 分钟
        </span>
      </div>
      <div style={CARD_BODY_STYLE}>
        <p style={{ fontSize: 13, color: '#374151', lineHeight: 1.7, margin: '0 0 12px' }}>
          {result.summary}
        </p>
        {priorityFiles.length > 0 && (
          <>
            <p style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', margin: '0 0 6px' }}>重点关注文件</p>
            <ol style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {priorityFiles.map((f, i) => (
                <li key={i} style={{ fontSize: 12, color: '#374151', fontFamily: "'JetBrains Mono', Consolas, monospace" }}>
                  {f}
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </div>
  )
}

function RiskAnalysisCard({ riskAreas }: { riskAreas: RiskArea[] }) {
  const grouped: Record<string, RiskArea[]> = { HIGH: [], MEDIUM: [], LOW: [] }
  for (const r of riskAreas) grouped[r.level]?.push(r)

  return (
    <div style={CARD_STYLE}>
      <div style={CARD_HEADER_STYLE}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#F59E0B"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>
        风险分析
      </div>
      <div style={{ ...CARD_BODY_STYLE, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {(['HIGH', 'MEDIUM', 'LOW'] as const).map(level => {
          const items = grouped[level]
          if (!items || items.length === 0) return null
          const cfg = RISK_CONFIG[level]
          return (
            <div key={level}>
              <div style={{ fontSize: 11, fontWeight: 700, color: cfg.text, marginBottom: 6, letterSpacing: '0.05em' }}>
                {cfg.label} ({items.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {items.map((r, i) => (
                  <div
                    key={i}
                    style={{
                      background: cfg.bg, border: `1px solid ${cfg.border}`,
                      borderRadius: 6, padding: '8px 12px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                      <span
                        style={{
                          fontSize: 10, fontWeight: 700,
                          fontFamily: "'JetBrains Mono', Consolas, monospace",
                          color: cfg.text, flexShrink: 0,
                          maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}
                      >
                        {r.file}
                      </span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: '#0F172A' }}>{r.title}</span>
                    </div>
                    <p style={{ fontSize: 12, color: '#374151', margin: 0, lineHeight: 1.5 }}>{r.impact}</p>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
        {riskAreas.length === 0 && (
          <p style={{ fontSize: 13, color: '#94A3B8', textAlign: 'center', margin: '8px 0' }}>无风险项</p>
        )}
      </div>
    </div>
  )
}

function ReviewFindingsCard({
  issues,
  filterTab,
  setFilterTab,
  expandedId,
  setExpandedId,
}: {
  issues: ReviewIssue[]
  filterTab: FilterTab
  setFilterTab: (t: FilterTab) => void
  expandedId: string | null
  setExpandedId: (id: string | null) => void
}) {
  const [groupOpen, setGroupOpen] = useState<Record<Severity, boolean>>({ ERROR: true, WARNING: false, INFO: false })

  const counts = {
    all: issues.length,
    ERROR: issues.filter(i => i.severity === 'ERROR').length,
    WARNING: issues.filter(i => i.severity === 'WARNING').length,
    INFO: issues.filter(i => i.severity === 'INFO').length,
  }

  const filtered = filterTab === 'all' ? issues : issues.filter(i => i.severity === filterTab)
  const byGroup: Record<Severity, ReviewIssue[]> = { ERROR: [], WARNING: [], INFO: [] }
  for (const issue of filtered) byGroup[issue.severity].push(issue)

  const tabConfig: [FilterTab, string][] = [
    ['all', `全部 ${counts.all}`],
    ['ERROR', `严重 ${counts.ERROR}`],
    ['WARNING', `警告 ${counts.WARNING}`],
    ['INFO', `提示 ${counts.INFO}`],
  ]

  const groupMeta: { sev: Severity; label: string }[] = [
    { sev: 'ERROR', label: 'Critical' },
    { sev: 'WARNING', label: 'Warning' },
    { sev: 'INFO', label: 'Suggestion' },
  ]

  return (
    <div style={CARD_STYLE}>
      <div style={{ ...CARD_HEADER_STYLE, flexWrap: 'wrap', gap: 8 }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#EF4444"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
        审查发现
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {tabConfig.map(([tab, label]) => (
            <button
              key={tab}
              onClick={() => setFilterTab(tab)}
              style={{
                padding: '3px 10px', borderRadius: 20,
                border: filterTab === tab ? '1px solid #BFDBFE' : '1px solid #E5E7EB',
                background: filterTab === tab ? '#EFF6FF' : 'transparent',
                color: filterTab === tab ? '#2563EB' : '#64748B',
                fontSize: 11, fontWeight: filterTab === tab ? 700 : 400,
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div>
        {groupMeta.map(({ sev, label }) => {
          const items = byGroup[sev]
          if (items.length === 0) return null
          const isOpen = groupOpen[sev]
          const cfg = SEV_COLOR[sev]
          return (
            <div key={sev} style={{ borderBottom: '1px solid #F1F5F9' }}>
              <button
                onClick={() => setGroupOpen(g => ({ ...g, [sev]: !g[sev] }))}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                  padding: '8px 16px', background: '#FAFAFA',
                  border: 'none', cursor: 'pointer', textAlign: 'left',
                }}
              >
                <span
                  style={{
                    background: cfg.bg, color: cfg.text,
                    fontSize: 10, fontWeight: 700,
                    padding: '2px 8px', borderRadius: 4,
                  }}
                >
                  {label}
                </span>
                <span style={{ fontSize: 12, color: '#374151' }}>({items.length})</span>
                <svg
                  width="13" height="13" viewBox="0 0 24 24" fill="#94A3B8"
                  style={{ marginLeft: 'auto', transform: isOpen ? 'none' : 'rotate(-90deg)', transition: 'transform 0.15s' }}
                >
                  <path d="M7 10l5 5 5-5z"/>
                </svg>
              </button>
              {isOpen && items.map((issue, i) => {
                const id = `${issue.file}:${issue.line}:${sev}:${i}`
                return (
                  <IssueRow
                    key={id}
                    issue={issue}
                    expanded={expandedId === id}
                    onToggle={() => setExpandedId(expandedId === id ? null : id)}
                  />
                )
              })}
            </div>
          )
        })}
        {filtered.length === 0 && (
          <div style={{ padding: '20px 16px', textAlign: 'center', color: '#94A3B8', fontSize: 13 }}>
            该分类下暂无问题
          </div>
        )}
      </div>
    </div>
  )
}

function MergeRecommendationCard({ rec }: { rec: MergeRecommendation }) {
  const cfg = DECISION_CONFIG[rec.decision] ?? DECISION_CONFIG.COMMENT

  return (
    <div style={CARD_STYLE}>
      <div style={CARD_HEADER_STYLE}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#059669"><path d="M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z"/></svg>
        合并建议
      </div>
      <div style={{ ...CARD_BODY_STYLE, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span
            style={{
              background: cfg.bg, color: cfg.text,
              border: `1px solid ${cfg.border}`,
              fontSize: 12, fontWeight: 700,
              padding: '5px 14px', borderRadius: 6,
              letterSpacing: '0.04em',
            }}
          >
            {cfg.label}
          </span>
          <span style={{ fontSize: 13, color: '#374151' }}>置信度</span>
          <div style={{ flex: 1, background: '#F1F5F9', borderRadius: 99, height: 8, overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                width: `${rec.confidence}%`,
                background: rec.decision === 'APPROVE' ? '#059669' : rec.decision === 'REQUEST_CHANGES' ? '#EF4444' : '#F59E0B',
                borderRadius: 99,
                transition: 'width 0.6s ease',
              }}
            />
          </div>
          <span style={{ fontSize: 12, fontWeight: 700, color: '#374151', flexShrink: 0 }}>{rec.confidence}%</span>
        </div>

        {rec.reasons.length > 0 && (
          <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 5 }}>
            {rec.reasons.map((r, i) => (
              <li key={i} style={{ fontSize: 13, color: '#374151', lineHeight: 1.5 }}>{r}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────────

function buildMarkdown(result: ReviewResult, prUrl: string, meta: PRMeta | null): string {
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

export default function ReviewResultsPanel({ prUrl, meta, githubToken, onDiffLoaded }: Props) {
  const { model, apiKey, baseUrl } = useSettings()
  const [result, setResult] = useState<ReviewResult | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [thinkText, setThinkText] = useState('')
  const [thinkDone, setThinkDone] = useState(false)
  const [thinkCollapsed, setThinkCollapsed] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [filterTab, setFilterTab] = useState<FilterTab>('all')
  const [streamError, setStreamError] = useState('')
  const [postLoading, setPostLoading] = useState(false)
  const [postMsg, setPostMsg] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const thinkRef = useRef<HTMLDivElement>(null)

  function handleViewInPR() {
    if (prUrl) window.open(prUrl, '_blank', 'noopener,noreferrer')
  }

  function handleExport() {
    if (!result || !prUrl) return
    const md = buildMarkdown(result, prUrl, meta)
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `pr-review-${Date.now()}.md`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  async function handlePostReview() {
    if (!result || !prUrl || !githubToken || postLoading) return
    setPostLoading(true)
    setPostMsg('')
    try {
      const res = await fetch('/api/review/post', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pr_url: prUrl,
          github_token: githubToken,
          result: {
            summary: result.summary,
            risk_level: result.risk_level,
            issues: result.issues,
            stats: result.stats,
          },
        }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== '0') throw new Error(json.detail || '提交失败')
      setPostMsg('评审已提交到 GitHub ✓')
      if (json.data?.html_url) window.open(json.data.html_url, '_blank', 'noopener,noreferrer')
    } catch (e: unknown) {
      setPostMsg((e as Error).message || '提交失败，请重试')
    } finally {
      setPostLoading(false)
    }
  }

  async function startReview() {
    if (!prUrl || !meta || streaming) return
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setStreaming(true)
    setResult(null)
    setThinkText('')
    setThinkDone(false)
    setThinkCollapsed(false)
    setStreamError('')
    setFilterTab('all')

    try {
      const res = await fetch('/api/review/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pr_url: prUrl,
          model: model || 'deepseek-v4-flash',
          api_key: apiKey || undefined,
          base_url: baseUrl || undefined,
        }),
        signal: ctrl.signal,
      })
      if (!res.ok) throw new Error(`请求失败: ${res.status}`)

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let resultAccumulated = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() ?? ''

        for (const part of parts) {
          const line = part.trim()
          if (!line.startsWith('data:')) continue
          const raw = line.slice(5).trim()

          if (raw === '[DONE]') {
            try {
              let jsonStr = resultAccumulated.trim()
              // Strip markdown fences if present
              const fenceMatch = jsonStr.match(/```(?:json)?\s*([\s\S]*?)```/)
              if (fenceMatch) {
                jsonStr = fenceMatch[1].trim()
              } else {
                // Fallback: extract the outermost JSON object
                const start = jsonStr.indexOf('{')
                const end = jsonStr.lastIndexOf('}')
                if (start !== -1 && end > start) jsonStr = jsonStr.slice(start, end + 1)
              }
              const parsed = JSON.parse(jsonStr) as ReviewResult
              setResult(parsed)
              setThinkDone(true)
              setTimeout(() => setThinkCollapsed(true), 600)
            } catch {
              setStreamError('结果解析失败，请重试')
            }
            setStreaming(false)
            return
          }

          try {
            const evt = JSON.parse(raw)
            if (evt.type === 'diff' && evt.lines && onDiffLoaded) {
              onDiffLoaded(parseDiffToMap(evt.lines as string[]))
            } else if (evt.type === 'thinking') {
              setThinkText(t => t + evt.delta)
              setTimeout(() => {
                if (thinkRef.current) thinkRef.current.scrollTop = thinkRef.current.scrollHeight
              }, 0)
            } else if (evt.type === 'result') {
              resultAccumulated += evt.delta
              setThinkDone(true)
            }
          } catch { /* skip */ }
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name !== 'AbortError') {
        setStreamError((e as Error).message || '分析失败，请重试')
      }
      setStreaming(false)
    }
  }

  const canStart = !!prUrl && !!meta && !streaming
  const allIssues = result?.issues ?? []

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div
        style={{
          flex: 1,
          background: '#fff',
          border: '1px solid #E5E7EB',
          borderRadius: 12,
          boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          minHeight: 0,
        }}
      >
        {/* Header */}
        <div
          style={{
            borderBottom: '1px solid #F1F5F9',
            padding: '12px 20px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>AI Code Review</span>
            <SettingsDrawer />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {result && (
              <>
                <button onClick={handleViewInPR} style={btnStyle} title="在 GitHub 中查看 PR">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/></svg>
                  在 PR 中查看
                </button>
                <button onClick={handleExport} style={btnStyle} title="导出 Markdown 报告">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
                  导出报告
                </button>
                <button
                  onClick={handlePostReview}
                  disabled={!githubToken || postLoading}
                  title={!githubToken ? '需要配置 GitHub Token' : '提交评审到 GitHub'}
                  style={{
                    ...btnStyle,
                    opacity: !githubToken ? 0.5 : 1,
                    cursor: !githubToken || postLoading ? 'not-allowed' : 'pointer',
                    color: postMsg.includes('✓') ? '#059669' : '#374151',
                  }}
                >
                  {postLoading
                    ? <span style={{ width: 10, height: 10, border: '2px solid #E5E7EB', borderTopColor: '#374151', borderRadius: '50%', animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />
                    : <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
                  }
                  {postMsg || (postLoading ? '提交中…' : '生成评审')}
                </button>
              </>
            )}
            <button
              onClick={startReview}
              disabled={!canStart}
              style={{
                height: 34,
                padding: '0 16px',
                borderRadius: 8,
                border: 'none',
                cursor: canStart ? 'pointer' : 'not-allowed',
                background: canStart
                  ? 'linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%)'
                  : '#F1F5F9',
                color: canStart ? '#fff' : '#94A3B8',
                fontSize: 13,
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 7,
                boxShadow: canStart ? '0 2px 8px rgba(37,99,235,0.28)' : 'none',
                transition: 'all 0.15s',
              }}
            >
              {streaming ? (
                <>
                  <span
                    style={{
                      width: 12, height: 12,
                      border: '2px solid rgba(255,255,255,0.3)',
                      borderTopColor: '#fff',
                      borderRadius: '50%',
                      animation: 'spin 0.7s linear infinite',
                      display: 'inline-block',
                    }}
                  />
                  分析中…
                </>
              ) : (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/></svg>
                  开始 AI 审查
                </>
              )}
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px 20px',
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
            minHeight: 0,
          }}
        >
          {/* 连接中骨架 — streaming 已触发但 think 内容还未到达 */}
          {streaming && !thinkText && !thinkDone && (
            <div style={{ ...CARD_STYLE, padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{
                width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                background: '#8B5CF6', animation: 'pulse 1.2s ease-in-out infinite',
              }} />
              <span style={{ fontSize: 12, color: '#6D28D9', fontWeight: 600 }}>正在连接模型…</span>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6, marginLeft: 8 }}>
                {[100, 80, 60].map((w, i) => (
                  <div key={i} style={{
                    height: 10, borderRadius: 4, background: '#E9D5FF',
                    width: `${w}%`, animation: `pulse ${1.2 + i * 0.2}s ease-in-out infinite`,
                  }} />
                ))}
              </div>
            </div>
          )}

          {/* ThinkingPanel — 有内容后替换骨架 */}
          {(streaming || thinkDone) && thinkText && (
            <ThinkingPanel
              thinkText={thinkText}
              streaming={streaming}
              thinkDone={thinkDone}
              thinkCollapsed={thinkCollapsed}
              setThinkCollapsed={setThinkCollapsed}
              thinkRef={thinkRef}
            />
          )}

          {/* AISummaryCard */}
          {result && <AISummaryCard result={result} meta={meta} />}

          {/* RiskAnalysisCard */}
          {result && result.risk_areas && result.risk_areas.length > 0 && (
            <RiskAnalysisCard riskAreas={result.risk_areas} />
          )}

          {/* ReviewFindingsCard */}
          {result && allIssues.length > 0 && (
            <ReviewFindingsCard
              issues={allIssues}
              filterTab={filterTab}
              setFilterTab={setFilterTab}
              expandedId={expandedId}
              setExpandedId={setExpandedId}
            />
          )}

          {/* MergeRecommendationCard */}
          {result && result.merge_recommendation && (
            <MergeRecommendationCard rec={result.merge_recommendation} />
          )}

          {/* Empty state */}
          {!streaming && !result && !streamError && (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
              <div style={{ textAlign: 'center' }}>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="#CBD5E1" style={{ margin: '0 auto 10px', display: 'block' }}>
                  <path d="M20 8h-2.81c-.45-.78-1.07-1.45-1.82-1.96L17 4.41 15.59 3l-2.17 2.17C12.96 5.06 12.49 5 12 5c-.49 0-.96.06-1.41.17L8.41 3 7 4.41l1.62 1.63C7.88 6.55 7.26 7.22 6.81 8H4v2h2.09c-.05.33-.09.66-.09 1v1H4v2h2v1c0 .34.04.67.09 1H4v2h2.81c1.04 1.79 2.97 3 5.19 3s4.15-1.21 5.19-3H20v-2h-2.09c.05-.33.09-.66.09-1v-1h2v-2h-2v-1c0-.34-.04-.67-.09-1H20V8z"/>
                </svg>
                <p style={{ color: '#94A3B8', fontSize: 13 }}>
                  {meta ? '点击"开始 AI 审查"开始分析' : '粘贴 PR 链接以开始审查'}
                </p>
              </div>
            </div>
          )}

          {/* Error state */}
          {streamError && (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
              <div style={{ textAlign: 'center' }}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="#FCA5A5" style={{ margin: '0 auto 10px', display: 'block' }}>
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                </svg>
                <p style={{ color: '#EF4444', fontSize: 13 }}>{streamError}</p>
                <button
                  onClick={startReview}
                  style={{ marginTop: 10, fontSize: 12, color: '#2563EB', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                >
                  重试
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

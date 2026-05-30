import { useState } from 'react'
import { message } from 'antd'
import type { ReviewResult, Severity } from '../../types/review'
import IssueCard from './IssueCard'

interface Props {
  result: ReviewResult
  prUrl?: string
  githubToken?: string
  onRerun?: () => void
  lastSyncedAt?: number
}

const FILTERS: { label: string; value: Severity | 'ALL'; activeColor: string }[] = [
  { label: 'All',      value: 'ALL',     activeColor: '#334155' },
  { label: 'Critical', value: 'ERROR',   activeColor: '#ef4444' },
  { label: 'Warning',  value: 'WARNING', activeColor: '#f59e0b' },
  { label: 'Info',     value: 'INFO',    activeColor: '#3b82f6' },
]

type SortMode = 'severity' | 'file'

export default function ReviewResults({ result, prUrl, githubToken, onRerun, lastSyncedAt }: Props) {
  const [filter, setFilter] = useState<Severity | 'ALL'>('ALL')
  const [sortMode, setSortMode] = useState<SortMode>('severity')
  const [posting, setPosting] = useState(false)

  const counts = {
    ALL:     result.issues.length,
    ERROR:   result.stats.issues_by_severity['ERROR']   ?? 0,
    WARNING: result.stats.issues_by_severity['WARNING'] ?? 0,
    INFO:    result.stats.issues_by_severity['INFO']    ?? 0,
  }

  let displayed = filter === 'ALL'
    ? result.issues
    : result.issues.filter(i => i.severity === filter)

  if (sortMode === 'severity') {
    const order: Record<Severity, number> = { ERROR: 0, WARNING: 1, INFO: 2 }
    displayed = [...displayed].sort((a, b) => order[a.severity] - order[b.severity])
  } else {
    displayed = [...displayed].sort((a, b) => (a.file ?? '').localeCompare(b.file ?? ''))
  }

  const syncLabel = lastSyncedAt ? (() => {
    const m = Math.floor((Date.now() - lastSyncedAt) / 60000)
    if (m < 1) return 'Last synced just now'
    if (m < 60) return `Last synced ${m} minute${m > 1 ? 's' : ''} ago`
    const h = Math.floor(m / 60)
    return `Last synced ${h} hour${h > 1 ? 's' : ''} ago`
  })() : null

  const handlePostToGithub = async () => {
    if (!prUrl || !githubToken) return
    setPosting(true)
    try {
      const resp = await fetch('/api/review/post', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pr_url: prUrl, github_token: githubToken, result }),
      })
      const data = await resp.json()
      if (data.code === '0') {
        const n = data.data?.inline_count ?? 0
        message.success(n > 0 ? `Posted ${n} inline comments` : 'Submitted to GitHub')
      } else {
        message.error(data.detail || 'Failed to post')
      }
    } catch {
      message.error('Network error')
    } finally {
      setPosting(false)
    }
  }

  const handleExport = () => {
    const text = [
      '# PR Review Report\n',
      `**Summary:** ${result.summary}\n**Risk Level:** ${result.risk_level}\n**Issues:** ${result.issues.length}\n`,
      ...result.issues.map((issue, i) =>
        `## ${i + 1}. [${issue.severity}] ${issue.title}\n**File:** ${issue.file ?? 'N/A'}${issue.line ? ` Line ${issue.line}` : ''}\n\n${issue.description}\n${issue.suggestion ? `**Suggestion:** ${issue.suggestion}\n` : ''}`
      ),
    ].join('\n')
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(new Blob([text], { type: 'text/markdown' })),
      download: 'pr-review-report.md',
    })
    a.click()
  }

  const handleGeneratePatch = () => {
    const patches = result.issues.filter(i => i.diff_snippet)
      .map(i => `# ${i.title}\n${i.diff_snippet}`).join('\n\n---\n\n')
    if (!patches) { message.info('No patches available'); return }
    navigator.clipboard.writeText(patches).then(() => message.success('All patches copied'))
  }

  return (
    <div className="w-full animate-fade-up">
      {/* ── Results header ── */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <span style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>Review Results</span>
          <span style={{
            background: '#fff7ed', color: '#ea580c',
            border: '1px solid #fed7aa',
            borderRadius: 20, padding: '2px 10px', fontSize: 11, fontWeight: 700,
          }}>
            {result.issues.length} issues found
          </span>
        </div>

        <div className="flex items-center gap-2">
          {syncLabel && (
            <span style={{ fontSize: 11, color: '#94a3b8' }}>{syncLabel}</span>
          )}
          {onRerun && (
            <button
              onClick={onRerun}
              className="flex items-center gap-1.5"
              style={{
                padding: '5px 11px', borderRadius: 7, fontSize: 12,
                border: '1px solid #e2e8f0', background: '#ffffff',
                color: '#475569', cursor: 'pointer', fontWeight: 500,
                boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
              }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/>
              </svg>
              Sync with PR
            </button>
          )}
        </div>
      </div>

      {/* ── Filter tabs + Sort ── */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div
          className="flex items-center gap-0.5 p-1 rounded-lg"
          style={{ background: '#f1f5f9', border: '1px solid #e2e8f0' }}
        >
          {FILTERS.map(({ label, value, activeColor }) => {
            const count = counts[value]
            const active = filter === value
            return (
              <button
                key={value}
                onClick={() => setFilter(value)}
                style={{
                  padding: '4px 10px', borderRadius: 6, fontSize: 12,
                  border: 'none',
                  background: active ? '#ffffff' : 'transparent',
                  color: active ? activeColor : '#64748b',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                  fontWeight: active ? 700 : 400,
                  boxShadow: active ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                  transition: 'all 0.1s',
                }}
              >
                {label}
                <span style={{
                  background: active ? activeColor : '#e2e8f0',
                  color: active ? '#fff' : '#64748b',
                  borderRadius: 10, padding: '1px 6px', fontSize: 10, fontWeight: 700,
                }}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>

        <div className="flex items-center gap-1.5">
          <span style={{ fontSize: 11, color: '#94a3b8' }}>Sort by:</span>
          <select
            value={sortMode}
            onChange={e => setSortMode(e.target.value as SortMode)}
            style={{
              background: '#ffffff', border: '1px solid #e2e8f0',
              borderRadius: 6, padding: '4px 8px', fontSize: 11,
              color: '#475569', cursor: 'pointer', outline: 'none',
              boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
            }}
          >
            <option value="severity">Severity</option>
            <option value="file">File Path</option>
          </select>
        </div>
      </div>

      {/* ── Issue list ── */}
      {displayed.map((issue, i) => (
        <IssueCard key={i} issue={issue} prUrl={prUrl} />
      ))}

      {displayed.length === 0 && (
        <div className="text-center py-12">
          <span style={{ color: '#94a3b8', fontSize: 13 }}>No issues match this filter</span>
        </div>
      )}

      {/* ── Bottom action bar ── */}
      <div
        className="flex items-center justify-between mt-5 pt-4 flex-wrap gap-2"
        style={{ borderTop: '1px solid #e2e8f0' }}
      >
        <span style={{ color: '#94a3b8', fontSize: 12 }}>
          {result.issues.length} issue{result.issues.length !== 1 ? 's' : ''} found
        </span>

        <div className="flex items-center gap-2">
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5"
            style={{
              padding: '6px 12px', borderRadius: 7, fontSize: 12,
              border: '1px solid #e2e8f0', background: '#ffffff',
              color: '#475569', cursor: 'pointer', fontWeight: 500,
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
            </svg>
            Export Report
          </button>

          {prUrl && githubToken && (
            <button
              onClick={handlePostToGithub}
              disabled={posting}
              className="flex items-center gap-1.5"
              style={{
                padding: '6px 12px', borderRadius: 7, fontSize: 12,
                border: '1px solid #e2e8f0', background: '#ffffff',
                color: '#475569', cursor: posting ? 'not-allowed' : 'pointer', fontWeight: 500,
                boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
              }}
            >
              Generate PR Review Comment
            </button>
          )}

          <button
            onClick={handleGeneratePatch}
            className="flex items-center gap-1.5"
            style={{
              padding: '6px 14px', borderRadius: 7, fontSize: 12,
              border: 'none',
              background: 'linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%)',
              color: '#ffffff', cursor: 'pointer', fontWeight: 600,
              boxShadow: '0 2px 6px rgba(79,70,229,0.3)',
            }}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
              <path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/>
            </svg>
            Generate Patch (Unified Diff)
          </button>
        </div>
      </div>
    </div>
  )
}

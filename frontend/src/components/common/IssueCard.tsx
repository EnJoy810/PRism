import { useState } from 'react'
import { message } from 'antd'
import type { ReviewIssue, Severity } from '../../types/review'

const severityCfg: Record<Severity, {
  label: string; badgeBg: string; badgeColor: string;
  cardBg: string; cardBorder: string;
}> = {
  ERROR: {
    label: 'Critical',
    badgeBg: '#ef4444', badgeColor: '#fff',
    cardBg: '#fff',    cardBorder: '#e2e8f0',
  },
  WARNING: {
    label: 'Warning',
    badgeBg: '#f59e0b', badgeColor: '#fff',
    cardBg: '#fff',    cardBorder: '#e2e8f0',
  },
  INFO: {
    label: 'Info',
    badgeBg: '#3b82f6', badgeColor: '#fff',
    cardBg: '#fff',    cardBorder: '#e2e8f0',
  },
}

const categoryColors: Record<string, { bg: string; color: string; border: string }> = {
  Security:    { bg: '#f5f3ff', color: '#7c3aed', border: '#ddd6fe' },
  Performance: { bg: '#eff6ff', color: '#2563eb', border: '#bfdbfe' },
  'Code Smell':{ bg: '#fff7ed', color: '#c2410c', border: '#fed7aa' },
  Style:       { bg: '#f0fdf4', color: '#15803d', border: '#bbf7d0' },
  Bug:         { bg: '#fef2f2', color: '#b91c1c', border: '#fecaca' },
  Logic:       { bg: '#fdf4ff', color: '#a21caf', border: '#f5d0fe' },
}

function inferCategory(issue: ReviewIssue): string {
  const t = `${issue.title} ${issue.description}`.toLowerCase()
  if (t.includes('injection') || t.includes('xss') || t.includes('auth') || t.includes('vulnerab') || t.includes('sql')) return 'Security'
  if (t.includes('performance') || t.includes('slow') || t.includes('n+1') || t.includes('cache')) return 'Performance'
  if (t.includes('complexity') || t.includes('duplicate') || t.includes('cognitive')) return 'Code Smell'
  if (t.includes('style') || t.includes('naming') || t.includes('chaining') || t.includes('operator')) return 'Style'
  if (t.includes('bug') || t.includes('error') || t.includes('crash') || t.includes('null')) return 'Bug'
  return 'Logic'
}

function DiffLines({ snippet }: { snippet: string }) {
  return (
    <div
      style={{
        fontFamily: "'JetBrains Mono','Fira Code',Consolas,monospace",
        fontSize: 12, lineHeight: '19px',
        background: '#0d1117',
        borderRadius: 8, border: '1px solid #21262d',
        overflow: 'auto', maxHeight: 200,
        marginBottom: 12,
      }}
    >
      {snippet.split('\n').map((line, i) => {
        let bg = 'transparent', color = '#c9d1d9'
        if (line.startsWith('+')) { bg = 'rgba(46,160,67,0.15)'; color = '#aff5b4' }
        else if (line.startsWith('-')) { bg = 'rgba(248,81,73,0.15)'; color = '#ffa198' }
        else if (line.startsWith('@@')) color = '#79c0ff'
        return (
          <div key={i} style={{ display: 'flex', background: bg }}>
            <span style={{
              width: 38, textAlign: 'right', paddingRight: 10, paddingLeft: 8,
              color: '#636e7b', userSelect: 'none', flexShrink: 0, fontSize: 11,
              lineHeight: '19px',
            }}>
              {!line.startsWith('@@') ? i + 1 : ''}
            </span>
            <span style={{ color, whiteSpace: 'pre', paddingRight: 16 }}>{line || ' '}</span>
          </div>
        )
      })}
    </div>
  )
}

export default function IssueCard({ issue, prUrl }: { issue: ReviewIssue; prUrl?: string }) {
  const cfg = severityCfg[issue.severity]
  const [expanded, setExpanded] = useState(issue.severity === 'ERROR')
  const category = inferCategory(issue)
  const cat = categoryColors[category] ?? categoryColors.Logic

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(
      `[${issue.severity}] ${issue.title}\n\n${issue.description}${issue.suggestion ? `\n\nSuggestion: ${issue.suggestion}` : ''}`
    ).then(() => message.success('Copied'))
  }

  const handleApplyPatch = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (issue.diff_snippet) {
      navigator.clipboard.writeText(issue.diff_snippet).then(() => message.success('Patch copied'))
    } else {
      message.info('No patch available')
    }
  }

  return (
    <div
      className="mb-2 rounded-xl overflow-hidden"
      style={{
        background: cfg.cardBg,
        border: `1px solid ${cfg.cardBorder}`,
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
      }}
    >
      {/* Header row */}
      <div
        className="flex items-center gap-2 px-4 py-3 cursor-pointer"
        onClick={() => setExpanded(e => !e)}
        style={{ userSelect: 'none' }}
      >
        {/* Severity badge */}
        <span style={{
          padding: '3px 9px', borderRadius: 5, fontSize: 11, fontWeight: 700,
          background: cfg.badgeBg, color: cfg.badgeColor, flexShrink: 0,
        }}>
          {cfg.label}
        </span>

        {/* File + line */}
        {issue.file && (
          <code style={{ fontSize: 11, color: '#64748b', flexShrink: 0 }}>
            {issue.file}{issue.line != null ? ` · Line ${issue.line}` : ''}
          </code>
        )}

        {/* Category tag */}
        <span style={{
          padding: '2px 8px', borderRadius: 10, fontSize: 10, fontWeight: 600,
          background: cat.bg, color: cat.color, border: `1px solid ${cat.border}`, flexShrink: 0,
        }}>
          {category}
        </span>

        <span style={{ flex: 1 }} />

        {/* Copy button */}
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5"
          style={{
            background: '#f8fafc', border: '1px solid #e2e8f0',
            cursor: 'pointer', padding: '4px 9px', borderRadius: 6,
            color: '#64748b', fontSize: 11, fontWeight: 500,
          }}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
            <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>
          </svg>
          Copy
        </button>

        {/* Chevron */}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="#94a3b8">
          <path d={expanded ? 'M7 14l5-5 5 5z' : 'M7 10l5 5 5-5z'}/>
        </svg>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div className="px-4 pb-4" style={{ borderTop: '1px solid #f1f5f9' }}>
          <div style={{ height: 10 }} />

          {/* Title + diff mode toggle */}
          <div className="flex items-start justify-between gap-3 mb-3">
            <span style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', lineHeight: 1.5 }}>
              {issue.title}
            </span>
            {issue.diff_snippet && (
              <span
                style={{
                  flexShrink: 0, background: '#f1f5f9', border: '1px solid #e2e8f0',
                  borderRadius: 6, padding: '3px 10px', fontSize: 11,
                  color: '#64748b', cursor: 'pointer', whiteSpace: 'nowrap',
                  display: 'flex', alignItems: 'center', gap: 4,
                }}
              >
                Unified diff
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M7 10l5 5 5-5z"/>
                </svg>
              </span>
            )}
          </div>

          {issue.diff_snippet && <DiffLines snippet={issue.diff_snippet} />}

          <p style={{ color: '#334155', fontSize: 13, marginBottom: 12, lineHeight: 1.65 }}>
            {issue.description}
          </p>

          {issue.suggestion && (
            <div style={{
              background: '#fffbeb', borderRadius: 8,
              padding: '8px 12px', border: '1px solid #fde68a', marginBottom: 12,
            }}>
              <span style={{ color: '#92400e', fontSize: 12 }}>💡 {issue.suggestion}</span>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleApplyPatch}
              className="flex items-center gap-1.5"
              style={{
                background: '#4f46e5', color: '#ffffff',
                border: 'none', borderRadius: 7, padding: '6px 14px',
                fontSize: 12, fontWeight: 600, cursor: 'pointer',
                boxShadow: '0 1px 4px rgba(79,70,229,0.3)',
              }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <path d="M13 10h5l-6 6-6-6h5V3h2v7zM5 19h14v2H5z"/>
              </svg>
              Apply Patch
            </button>

            {prUrl && (
              <a
                href={`${prUrl}/files`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5"
                style={{
                  background: '#ffffff', border: '1px solid #e2e8f0',
                  borderRadius: 7, padding: '5px 14px',
                  fontSize: 12, color: '#475569', fontWeight: 500,
                  textDecoration: 'none',
                }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
                </svg>
                View in PR
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

import { useState } from 'react'
import { Typography, message } from 'antd'
import { CopyOutlined, LinkOutlined } from '@ant-design/icons'
import type { ReviewIssue, Severity } from '../../types/review'

const { Text, Paragraph } = Typography

const severityConfig: Record<Severity, { bg: string; border: string; dot: string; badgeBg: string; label: string }> = {
  ERROR:   { bg: 'rgba(239,68,68,0.05)',   border: 'rgba(239,68,68,0.18)',   dot: '#ef4444', badgeBg: 'rgba(239,68,68,0.12)',  label: 'Critical' },
  WARNING: { bg: 'rgba(245,158,11,0.05)',  border: 'rgba(245,158,11,0.18)',  dot: '#f59e0b', badgeBg: 'rgba(245,158,11,0.12)', label: 'Warning'  },
  INFO:    { bg: 'rgba(59,130,246,0.05)',  border: 'rgba(59,130,246,0.18)',  dot: '#3b82f6', badgeBg: 'rgba(59,130,246,0.12)', label: 'Info'     },
}

function DiffSnippet({ snippet }: { snippet: string }) {
  return (
    <div style={{
      fontFamily: "'JetBrains Mono','Fira Code',Consolas,monospace",
      fontSize: 12, lineHeight: '18px',
      background: '#0d1117', borderRadius: 6,
      border: '1px solid var(--hairline)',
      overflow: 'auto', maxHeight: 200,
      marginBottom: 10,
    }}>
      {snippet.split('\n').map((line, i) => {
        let bg = 'transparent'
        let color = '#c9d1d9'
        if (line.startsWith('+')) { bg = 'rgba(40,167,69,0.15)'; color = '#aff5b4' }
        else if (line.startsWith('-')) { bg = 'rgba(248,81,73,0.15)'; color = '#ffa198' }
        else if (line.startsWith('@@')) { color = '#79c0ff' }
        return (
          <div key={i} style={{ padding: '0 12px', background: bg, color, whiteSpace: 'pre' }}>
            {line || ' '}
          </div>
        )
      })}
    </div>
  )
}

interface IssueCardProps {
  issue: ReviewIssue
  prUrl?: string
}

export default function IssueCard({ issue, prUrl }: IssueCardProps) {
  const cfg = severityConfig[issue.severity]
  const [expanded, setExpanded] = useState(issue.severity === 'ERROR')

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    const text = `[${issue.severity}] ${issue.title}\n\n${issue.description}${issue.suggestion ? `\n\n建议：${issue.suggestion}` : ''}`
    navigator.clipboard.writeText(text).then(() => message.success('已复制'))
  }

  const issueLineUrl = prUrl && issue.file
    ? `${prUrl}/files#diff-${issue.file.replace(/\//g, '-')}`
    : undefined

  return (
    <div
      className="mb-2 rounded-lg overflow-hidden"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      {/* Header row — clickable */}
      <div
        className="flex items-center gap-2 px-3 py-2.5 cursor-pointer"
        onClick={() => setExpanded(e => !e)}
        style={{ userSelect: 'none' }}
      >
        {/* Severity badge */}
        <span style={{
          padding: '2px 7px', borderRadius: 4, fontSize: 11, fontWeight: 700,
          background: cfg.badgeBg, color: cfg.dot, flexShrink: 0,
        }}>
          {cfg.label}
        </span>

        {/* File + line */}
        {issue.file && (
          <code style={{ fontSize: 11, color: 'var(--ink-mute)', flexShrink: 0 }}>
            {issue.file}{issue.line != null ? ` · Line ${issue.line}` : ''}
          </code>
        )}

        {/* Title */}
        <Text style={{ color: 'var(--ink)', fontSize: 12, fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {issue.title}
        </Text>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0" onClick={e => e.stopPropagation()}>
          <button
            onClick={handleCopy}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px', color: 'var(--ink-stone)', borderRadius: 3 }}
            title="复制"
          >
            <CopyOutlined style={{ fontSize: 12 }} />
          </button>
          <span style={{ color: 'var(--ink-stone)', fontSize: 11, marginLeft: 4 }}>
            {expanded ? '▲' : '▼'}
          </span>
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="px-3 pb-3" style={{ borderTop: `1px solid ${cfg.border}` }}>
          <div style={{ height: 8 }} />

          {issue.diff_snippet && <DiffSnippet snippet={issue.diff_snippet} />}

          <Paragraph style={{ color: 'var(--ink-body)', fontSize: 13, marginBottom: issue.suggestion ? 8 : 0 }}>
            {issue.description}
          </Paragraph>

          {issue.suggestion && (
            <div style={{ background: 'var(--surface)', borderRadius: 6, padding: '8px 10px', border: '1px solid var(--hairline)', marginBottom: 8 }}>
              <Text style={{ color: 'var(--ink-mute)', fontSize: 12 }}>💡 {issue.suggestion}</Text>
            </div>
          )}

          {issueLineUrl && (
            <div className="flex justify-end">
              <a
                href={issueLineUrl}
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: 11, color: 'var(--ink-ash)', display: 'flex', alignItems: 'center', gap: 3, textDecoration: 'none' }}
              >
                <LinkOutlined /> View in PR
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

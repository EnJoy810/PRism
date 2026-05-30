import { Typography } from 'antd'
import type { ReviewIssue, Severity } from '../../types/review'

const { Text, Paragraph } = Typography

const severityConfig: Record<Severity, { bg: string; border: string; dot: string; label: string }> = {
  ERROR:   { bg: 'rgba(239,68,68,0.07)',   border: 'rgba(239,68,68,0.22)',   dot: '#ef4444', label: 'ERROR'   },
  WARNING: { bg: 'rgba(245,158,11,0.07)',  border: 'rgba(245,158,11,0.22)',  dot: '#f59e0b', label: 'WARNING' },
  INFO:    { bg: 'rgba(59,130,246,0.07)',  border: 'rgba(59,130,246,0.22)',  dot: '#3b82f6', label: 'INFO'    },
}

interface IssueCardProps {
  issue: ReviewIssue
}

export default function IssueCard({ issue }: IssueCardProps) {
  const cfg = severityConfig[issue.severity]
  return (
    <div
      className="mb-3 rounded-lg p-3"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      <div className="flex items-start gap-3">
        {/* Severity dot */}
        <div className="mt-1 shrink-0 flex items-center gap-1.5">
          <span
            style={{
              width: 7, height: 7, borderRadius: '50%',
              background: cfg.dot,
              boxShadow: `0 0 4px ${cfg.dot}`,
              display: 'inline-block',
            }}
          />
          <Text style={{ color: cfg.dot, fontSize: 11, fontWeight: 600, letterSpacing: '0.04em' }}>
            {cfg.label}
          </Text>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 mb-1">
            <Text strong style={{ color: 'var(--ink)', fontSize: 13 }}>
              {issue.title}
            </Text>
            {(issue.file || issue.line != null) && (
              <code style={{
                fontSize: 11, color: 'var(--ink-mute)',
                background: 'var(--surface)', borderRadius: 4,
                padding: '1px 5px', border: '1px solid var(--hairline)',
              }}>
                {issue.file}{issue.line != null ? `:${issue.line}` : ''}
              </code>
            )}
          </div>
          <Paragraph style={{ color: 'var(--ink-body)', fontSize: 13, marginBottom: 6 }}>
            {issue.description}
          </Paragraph>
          {issue.suggestion && (
            <div style={{
              background: 'var(--surface)', borderRadius: 6,
              padding: '8px 10px', border: '1px solid var(--hairline)',
            }}>
              <Text style={{ color: 'var(--ink-mute)', fontSize: 12 }}>
                {issue.suggestion}
              </Text>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

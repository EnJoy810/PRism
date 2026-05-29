import { Card, Tag, Typography } from 'antd'
import type { ReviewIssue, Severity } from '../../types/review'

const { Text, Paragraph } = Typography

const severityConfig: Record<Severity, { color: string; label: string }> = {
  ERROR: { color: '#ef4444', label: 'Error' },
  WARNING: { color: '#f59e0b', label: 'Warning' },
  INFO: { color: '#3b82f6', label: 'Info' },
}

interface IssueCardProps {
  issue: ReviewIssue
}

export default function IssueCard({ issue }: IssueCardProps) {
  const cfg = severityConfig[issue.severity]
  return (
    <Card
      className="mb-3"
      styles={{ body: { padding: '12px 16px' } }}
      style={{ borderLeft: `4px solid ${cfg.color}`, background: '#1e293b', borderColor: '#334155' }}
    >
      <div className="flex items-start gap-3">
        <Tag color={cfg.color} className="shrink-0 mt-0.5">
          {cfg.label}
        </Tag>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 mb-1">
            <Text strong className="text-gray-100">
              {issue.title}
            </Text>
            <Text className="text-gray-500 text-sm">
              {issue.file}{issue.line != null ? `:${issue.line}` : ''}
            </Text>
          </div>
          <Paragraph className="text-gray-400 mb-2 text-sm">
            {issue.description}
          </Paragraph>
          {issue.suggestion && (
            <div className="bg-gray-800 rounded p-2">
              <Text className="text-gray-300 text-sm">
                <span className="text-brand-primary mr-1">💡</span>
                {issue.suggestion}
              </Text>
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}

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
      <div className="flex flex-col sm:flex-row items-start gap-2 sm:gap-3">
        <Tag color={cfg.color} className="shrink-0">{cfg.label}</Tag>
        <div className="min-w-0 flex-1 w-full">
          <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-2 mb-1">
            <Text strong className="text-gray-100 break-words">
              {issue.title}
            </Text>
            <Text className="text-gray-500 text-sm truncate">
              {issue.file}{issue.line != null ? `:${issue.line}` : ''}
            </Text>
          </div>
          <Paragraph className="text-gray-400 mb-2 text-sm">
            {issue.description}
          </Paragraph>
          {issue.suggestion && (
            <div className="bg-gray-800 rounded p-2 break-words">
              <Text className="text-gray-300 text-sm italic">
                {issue.suggestion}
              </Text>
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}

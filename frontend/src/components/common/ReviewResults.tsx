import { Card, Tag, Typography } from 'antd'
import type { ReviewResult } from '../../types/review'
import IssueCard from './IssueCard'

const { Text, Title } = Typography

const riskConfig = {
  HIGH: { color: '#ef4444', label: 'HIGH' },
  MEDIUM: { color: '#f59e0b', label: 'MEDIUM' },
  LOW: { color: '#22c55e', label: 'LOW' },
}

interface ReviewResultsProps {
  result: ReviewResult
}

export default function ReviewResults({ result }: ReviewResultsProps) {
  const risk = riskConfig[result.risk_level]

  return (
    <div className="w-full max-w-2xl mt-10">
      {/* Summary Card */}
      <Card
        className="mb-6"
        style={{ background: '#1e293b', borderColor: '#334155' }}
      >
        <div className="flex items-start justify-between mb-4">
          <Title level={4} className="text-gray-100 mb-0">
            Review Summary
          </Title>
          <Tag color={risk.color} className="text-sm font-semibold px-3 py-0.5">
            {risk.label}
          </Tag>
        </div>
        <Text className="text-gray-300 block mb-4">{result.summary}</Text>

        {/* Stats row */}
        <div className="flex gap-6 text-sm">
          <div>
            <Text className="text-gray-500">Files changed</Text>
            <Text className="text-gray-100 ml-2 font-semibold">{result.stats.files_changed}</Text>
          </div>
          <div>
            <Text className="text-green-400">+{result.stats.additions}</Text>
          </div>
          <div>
            <Text className="text-red-400">-{result.stats.deletions}</Text>
          </div>
          <div className="flex gap-3 ml-auto">
            {Object.entries(result.stats.issues_by_severity).map(([sev, count]) => {
              if (count === 0) return null
              const colors: Record<string, string> = { ERROR: '#ef4444', WARNING: '#f59e0b', INFO: '#3b82f6' }
              return (
                <Text key={sev} style={{ color: colors[sev] ?? '#9ca3af' }}>
                  {sev} {count}
                </Text>
              )
            })}
          </div>
        </div>
      </Card>

      {/* Issues */}
      <Title level={5} className="text-gray-100 mb-4">
        Issues ({result.issues.length})
      </Title>
      {result.issues.map((issue, index) => (
        <IssueCard key={index} issue={issue} />
      ))}
      {result.issues.length === 0 && (
        <Text className="text-gray-500">No issues found in this PR.</Text>
      )}
    </div>
  )
}

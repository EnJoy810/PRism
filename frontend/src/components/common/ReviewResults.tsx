import { useState } from 'react'
import { Card, Tag, Typography, Segmented } from 'antd'
import type { ReviewResult, Severity } from '../../types/review'
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
  const [filter, setFilter] = useState<Severity | 'ALL'>('ALL')

  const filteredIssues = filter === 'ALL'
    ? result.issues
    : result.issues.filter((i) => i.severity === filter)

  const filterOptions = [
    { label: `全部 (${result.issues.length})`, value: 'ALL' as const },
    ...(['ERROR', 'WARNING', 'INFO'] as Severity[]).map((s) => ({
      label: `${s} (${result.stats.issues_by_severity[s]})`,
      value: s as Severity | 'ALL',
    })),
  ]

  return (
    <div className="w-full max-w-2xl mt-10">
      {/* Summary Card */}
      <Card
        className="mb-6"
        style={{ background: '#1e293b', borderColor: '#334155' }}
      >
        <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
          <Title level={4} className="text-gray-100 mb-0">
            Review Summary
          </Title>
          <Tag color={risk.color} className="text-sm font-semibold px-3 py-0.5">
            {risk.label}
          </Tag>
        </div>
        <Text className="text-gray-300 block mb-5 leading-relaxed">
          {result.summary}
        </Text>

        {/* Stats grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="rounded-lg p-3 text-center" style={{ background: '#0f172a' }}>
            <Text className="text-gray-500 text-xs block">修改文件</Text>
            <Text className="text-gray-100 text-lg font-semibold">{result.stats.files_changed}</Text>
          </div>
          <div className="rounded-lg p-3 text-center" style={{ background: '#0f172a' }}>
            <Text className="text-gray-500 text-xs block">新增行</Text>
            <Text className="text-green-400 text-lg font-semibold">+{result.stats.additions}</Text>
          </div>
          <div className="rounded-lg p-3 text-center" style={{ background: '#0f172a' }}>
            <Text className="text-gray-500 text-xs block">删除行</Text>
            <Text className="text-red-400 text-lg font-semibold">-{result.stats.deletions}</Text>
          </div>
          <div className="rounded-lg p-3 text-center" style={{ background: '#0f172a' }}>
            <Text className="text-gray-500 text-xs block">发现问题</Text>
            <Text className="text-gray-100 text-lg font-semibold">
              {Object.values(result.stats.issues_by_severity).reduce((a, b) => a + b, 0)}
            </Text>
          </div>
        </div>
      </Card>

      {/* Issues section */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <Title level={5} className="text-gray-100 mb-0">
          问题列表
        </Title>
        <Segmented
          value={filter}
          onChange={(val) => setFilter(val as Severity | 'ALL')}
          options={filterOptions}
          style={{ background: '#1e293b' }}
          className="text-xs"
        />
      </div>

      {filteredIssues.map((issue, index) => (
        <IssueCard key={index} issue={issue} />
      ))}
      {filteredIssues.length === 0 && (
        <div className="text-center py-10">
          <Text className="text-gray-600">没有匹配的问题</Text>
        </div>
      )}
    </div>
  )
}

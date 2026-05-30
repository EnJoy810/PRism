import { useState } from 'react'
import { Button, Segmented, Typography, message } from 'antd'
import { SendOutlined } from '@ant-design/icons'
import type { ReviewResult, Severity } from '../../types/review'
import IssueCard from './IssueCard'

const { Text, Title } = Typography

const riskConfig = {
  HIGH:   { color: 'var(--accent-red)',    bg: 'var(--accent-red-bg)',    label: 'HIGH'   },
  MEDIUM: { color: 'var(--accent-yellow)', bg: 'var(--accent-yel-bg)',    label: 'MEDIUM' },
  LOW:    { color: 'var(--accent-green)',  bg: 'var(--accent-grn-bg)',    label: 'LOW'    },
}

interface ReviewResultsProps {
  result: ReviewResult
  prUrl?: string
  githubToken?: string
}

export default function ReviewResults({ result, prUrl, githubToken }: ReviewResultsProps) {
  const risk = riskConfig[result.risk_level]
  const [filter, setFilter] = useState<Severity | 'ALL'>('ALL')
  const [posting, setPosting] = useState(false)

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
        message.success('Review 已提交到 GitHub！')
      } else {
        message.error(data.detail || '提交失败')
      }
    } catch {
      message.error('网络错误')
    } finally {
      setPosting(false)
    }
  }

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
    <div className="w-full max-w-2xl mt-8 animate-fade-up">
      {/* Summary card */}
      <div
        className="rounded-xl mb-5 overflow-hidden"
        style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)' }}
      >
        {/* Risk strip */}
        <div
          className="flex items-center justify-between px-4 py-2.5"
          style={{ background: risk.bg, borderBottom: '1px solid var(--hairline)' }}
        >
          <div className="flex items-center gap-2">
            <span
              style={{
                width: 8, height: 8, borderRadius: '50%',
                background: risk.color, display: 'inline-block',
                boxShadow: `0 0 6px ${risk.color}`,
              }}
            />
            <Text style={{ color: risk.color, fontWeight: 600, fontSize: 12, letterSpacing: '0.06em' }}>
              {risk.label} RISK
            </Text>
          </div>
          <div className="flex items-center gap-3">
            <Text style={{ color: 'var(--ink-ash)', fontSize: 12 }}>
              {result.stats.files_changed} 文件
              &nbsp;·&nbsp;
              <span style={{ color: 'var(--accent-green)' }}>+{result.stats.additions}</span>
              &nbsp;
              <span style={{ color: 'var(--accent-red)' }}>-{result.stats.deletions}</span>
            </Text>
            {prUrl && githubToken && (
              <Button
                size="small"
                icon={<SendOutlined />}
                loading={posting}
                onClick={handlePostToGithub}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--hairline-str)',
                  color: 'var(--ink-mute)',
                  fontSize: 11,
                  height: 24,
                }}
              >
                提交到 GitHub
              </Button>
            )}
          </div>
        </div>

        {/* Summary text */}
        <div className="px-4 py-4">
          <Text style={{ color: 'var(--ink-body)', lineHeight: 1.7, fontSize: 13 }}>
            {result.summary}
          </Text>
        </div>
      </div>

      {/* Issues section */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
        <Title level={5} style={{ color: 'var(--ink)', marginBottom: 0, fontSize: 13, fontWeight: 600, letterSpacing: '0.03em' }}>
          问题列表
        </Title>
        <Segmented
          value={filter}
          onChange={(val) => setFilter(val as Severity | 'ALL')}
          options={filterOptions}
          className="text-xs"
        />
      </div>

      {filteredIssues.map((issue, index) => (
        <IssueCard key={index} issue={issue} />
      ))}

      {filteredIssues.length === 0 && (
        <div className="text-center py-10">
          <Text style={{ color: 'var(--ink-stone)' }}>没有匹配的问题</Text>
        </div>
      )}
    </div>
  )
}

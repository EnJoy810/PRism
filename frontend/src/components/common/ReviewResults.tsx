import { useState } from 'react'
import { Button, Typography, message } from 'antd'
import { SyncOutlined, SendOutlined } from '@ant-design/icons'
import type { ReviewResult, Severity } from '../../types/review'
import IssueCard from './IssueCard'

const { Text } = Typography

interface ReviewResultsProps {
  result: ReviewResult
  prUrl?: string
  githubToken?: string
  onRerun?: () => void
}

const severityFilters: { label: string; value: Severity | 'ALL' }[] = [
  { label: 'All', value: 'ALL' },
  { label: 'Critical', value: 'ERROR' },
  { label: 'Warning', value: 'WARNING' },
  { label: 'Info', value: 'INFO' },
]

export default function ReviewResults({ result, prUrl, githubToken, onRerun }: ReviewResultsProps) {
  const [filter, setFilter] = useState<Severity | 'ALL'>('ALL')
  const [posting, setPosting] = useState(false)

  const counts = {
    ALL: result.issues.length,
    ERROR: result.stats.issues_by_severity['ERROR'] ?? 0,
    WARNING: result.stats.issues_by_severity['WARNING'] ?? 0,
    INFO: result.stats.issues_by_severity['INFO'] ?? 0,
  }

  const filteredIssues = filter === 'ALL'
    ? result.issues
    : result.issues.filter(i => i.severity === filter)

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
        const inlineCount = data.data?.inline_count ?? 0
        message.success(inlineCount > 0 ? `已发布 ${inlineCount} 条 inline comment` : '已提交到 GitHub')
      } else {
        message.error(data.detail || '提交失败')
      }
    } catch {
      message.error('网络错误')
    } finally {
      setPosting(false)
    }
  }

  return (
    <div className="w-full animate-fade-up">
      {/* Header — filter tabs + sync button */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-1">
          {severityFilters.map(({ label, value }) => {
            const count = counts[value]
            const active = filter === value
            const dotColors: Record<string, string> = {
              ALL: 'var(--ink-mute)', ERROR: '#ef4444',
              WARNING: '#f59e0b', INFO: '#3b82f6',
            }
            return (
              <button
                key={value}
                onClick={() => setFilter(value)}
                style={{
                  padding: '4px 10px', borderRadius: 6, fontSize: 12,
                  border: `1px solid ${active ? 'var(--hairline-str)' : 'transparent'}`,
                  background: active ? 'var(--surface-el)' : 'transparent',
                  color: active ? 'var(--ink)' : 'var(--ink-ash)',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                  fontWeight: active ? 600 : 400,
                }}
              >
                {label}
                <span style={{
                  background: active ? dotColors[value] : 'var(--surface-el)',
                  color: active ? '#000' : 'var(--ink-stone)',
                  borderRadius: 10, padding: '1px 6px', fontSize: 11, fontWeight: 700,
                }}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>

        {onRerun && (
          <button
            onClick={onRerun}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '4px 10px', borderRadius: 6, fontSize: 12,
              border: '1px solid var(--hairline)', background: 'transparent',
              color: 'var(--ink-ash)', cursor: 'pointer',
            }}
          >
            <SyncOutlined style={{ fontSize: 11 }} /> Sync with PR
          </button>
        )}
      </div>

      {/* Issues list */}
      {filteredIssues.map((issue, i) => (
        <IssueCard key={i} issue={issue} prUrl={prUrl} />
      ))}

      {filteredIssues.length === 0 && (
        <div className="text-center py-12">
          <Text style={{ color: 'var(--ink-stone)' }}>没有匹配的问题</Text>
        </div>
      )}

      {/* Bottom action bar */}
      {result.issues.length > 0 && (
        <div
          className="flex items-center justify-between mt-4 pt-4 flex-wrap gap-2"
          style={{ borderTop: '1px solid var(--hairline)' }}
        >
          <Text style={{ color: 'var(--ink-stone)', fontSize: 12 }}>
            共发现 {result.issues.length} 个问题
          </Text>
          <div className="flex gap-2">
            {prUrl && githubToken && (
              <Button
                size="small"
                icon={<SendOutlined />}
                loading={posting}
                onClick={handlePostToGithub}
                style={{
                  background: 'var(--ink)', color: '#000',
                  border: 'none', fontWeight: 500, fontSize: 12,
                }}
              >
                Generate PR Review Comment
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

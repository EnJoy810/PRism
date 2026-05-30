import { Typography } from 'antd'
import type { ReviewIssue, WalkthroughEntry } from '../../types/review'
import IssueCard from './IssueCard'

const { Text } = Typography

interface PartialResult {
  summary?: string
  risk_level?: 'HIGH' | 'MEDIUM' | 'LOW'
  walkthrough?: WalkthroughEntry[]
  issues?: ReviewIssue[]
}

interface Props {
  partial: PartialResult
  isStreaming: boolean
}

const riskConfig = {
  HIGH:   { color: 'var(--accent-red)',    bg: 'var(--accent-red-bg)'  },
  MEDIUM: { color: 'var(--accent-yellow)', bg: 'var(--accent-yel-bg)'  },
  LOW:    { color: 'var(--accent-green)',  bg: 'var(--accent-grn-bg)'  },
}

export default function StreamingResults({ partial, isStreaming }: Props) {
  const risk = riskConfig[partial.risk_level ?? 'LOW']

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
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: risk.color, display: 'inline-block',
              boxShadow: `0 0 6px ${risk.color}`,
            }} />
            <Text style={{ color: risk.color, fontWeight: 600, fontSize: 12, letterSpacing: '0.06em' }}>
              {partial.risk_level ?? '...'} RISK
            </Text>
          </div>
          {isStreaming && (
            <Text style={{ color: 'var(--ink-ash)', fontSize: 11 }}>
              <span className="animate-pulse">▌</span> 分析中
            </Text>
          )}
        </div>

        {/* Summary text */}
        <div className="px-4 py-4">
          <Text style={{ color: 'var(--ink-body)', lineHeight: 1.7, fontSize: 13 }}>
            {partial.summary}
            {isStreaming && !partial.walkthrough && (
              <span className="animate-pulse" style={{ color: 'var(--ink-stone)' }}>▊</span>
            )}
          </Text>

          {/* Walkthrough */}
          {partial.walkthrough && partial.walkthrough.length > 0 && (
            <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--hairline)' }}>
              <Text style={{ color: 'var(--ink-ash)', fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', display: 'block', marginBottom: 6 }}>
                文件变更速览
              </Text>
              <div className="flex flex-col gap-1">
                {partial.walkthrough.map((entry, i) => (
                  <div key={i} className="flex items-baseline gap-2 min-w-0">
                    <code style={{
                      fontSize: 11, color: 'var(--ink-mute)',
                      background: 'var(--surface)', borderRadius: 3,
                      padding: '1px 4px', border: '1px solid var(--hairline)',
                      flexShrink: 0, maxWidth: '45%',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {entry.file.split('/').pop()}
                    </code>
                    <Text style={{ color: 'var(--ink-body)', fontSize: 12, lineHeight: 1.5 }}>
                      {entry.summary}
                    </Text>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Issues — 逐条渐现 */}
      {partial.issues && partial.issues.length > 0 && (
        <>
          <Text style={{ color: 'var(--ink)', fontSize: 13, fontWeight: 600, letterSpacing: '0.03em', display: 'block', marginBottom: 10 }}>
            问题列表
          </Text>
          {partial.issues.map((issue, i) => (
            <div key={i} className="animate-fade-up" style={{ animationDelay: `${i * 60}ms`, animationFillMode: 'both' }}>
              <IssueCard issue={issue} />
            </div>
          ))}
          {isStreaming && (
            <div className="text-center py-3">
              <Text style={{ color: 'var(--ink-stone)', fontSize: 12 }}>
                <span className="animate-pulse">▌</span> 继续分析中...
              </Text>
            </div>
          )}
        </>
      )}

      {/* 没有 issues 但还在 streaming，显示占位 */}
      {(!partial.issues || partial.issues.length === 0) && isStreaming && partial.walkthrough && (
        <div className="text-center py-6">
          <Text style={{ color: 'var(--ink-stone)', fontSize: 12 }}>
            <span className="animate-pulse">▌</span> 正在识别问题...
          </Text>
        </div>
      )}
    </div>
  )
}

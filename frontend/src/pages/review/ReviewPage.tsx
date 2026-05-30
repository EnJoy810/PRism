import { useRef, useState } from 'react'
import { useReviewStream } from '../../hooks/useReviewStream'
import ReviewForm from '../../components/common/ReviewForm'
import ReviewResults from '../../components/common/ReviewResults'
import DiffScannerPanel from '../../components/common/DiffScannerPanel'
import PRMetadataCard from '../../components/left/PRMetadataCard'
import ChangedFilesList from '../../components/left/ChangedFilesList'
import { Alert, Button, Spin } from 'antd'
import type { ReviewType } from '../../types/review'

export default function ReviewPage() {
  const { streamText, result, isStreaming, isPending, error,
          diffLines, diffTitle, cursorPath, prMeta, startStream, reset } = useReviewStream()
  const lastRef = useRef<{ prUrl: string; token?: string } | null>(null)
  const [reviewType, setReviewType] = useState<ReviewType>('all')

  const handleSubmit = (prUrl: string, githubToken?: string) => {
    lastRef.current = { prUrl, token: githubToken }
    startStream(prUrl, githubToken, reviewType)
  }

  const showDiffPanel = diffLines.length > 0 && !result
  const isActive = isPending || isStreaming || !!result

  return (
    <div className="min-h-screen" style={{ background: 'var(--canvas)' }}>
      {/* 两栏布局容器 */}
      <div className="flex gap-0 min-h-screen" style={{ maxWidth: 1280, margin: '0 auto' }}>

        {/* 左栏 45% */}
        <div className="flex flex-col p-6 gap-4" style={{ width: '45%', borderRight: '1px solid var(--hairline)', minHeight: '100vh' }}>

          {/* 步骤1：输入框 */}
          <div>
            <div className="text-xs font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--ink-ash)', letterSpacing: '0.06em' }}>
              <span style={{ width: 18, height: 18, borderRadius: '50%', background: 'var(--surface-el)', border: '1px solid var(--hairline)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: 'var(--ink-mute)' }}>1</span>
              PULL REQUEST
            </div>
            <ReviewForm onSubmit={handleSubmit} loading={isPending || isStreaming} />
          </div>

          {/* 步骤2：PR metadata（解析后出现） */}
          {prMeta && lastRef.current?.prUrl && (
            <div>
              <div className="text-xs font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--ink-ash)', letterSpacing: '0.06em' }}>
                <span style={{ width: 18, height: 18, borderRadius: '50%', background: 'var(--surface-el)', border: '1px solid var(--hairline)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: 'var(--ink-mute)' }}>2</span>
                PR 信息
                <span style={{ background: 'var(--accent-grn-bg)', color: 'var(--accent-green)', fontSize: 10, padding: '1px 6px', borderRadius: 4, fontWeight: 600 }}>Ready</span>
              </div>
              <PRMetadataCard meta={prMeta} prUrl={lastRef.current.prUrl} />
            </div>
          )}

          {/* 步骤3：变更文件列表 */}
          {prMeta && prMeta.files.length > 0 && (
            <div>
              <div className="text-xs font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--ink-ash)', letterSpacing: '0.06em' }}>
                <span style={{ width: 18, height: 18, borderRadius: '50%', background: 'var(--surface-el)', border: '1px solid var(--hairline)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: 'var(--ink-mute)' }}>3</span>
                变更文件 ({prMeta.files_changed})
              </div>
              <ChangedFilesList files={prMeta.files} />
            </div>
          )}
        </div>

        {/* 右栏 55% */}
        <div className="flex flex-col p-6" style={{ width: '55%' }}>

          {/* Review Type 配置栏 */}
          <div className="flex items-center gap-3 mb-6 flex-wrap">
            <span style={{ color: 'var(--ink-ash)', fontSize: 12, fontWeight: 600, letterSpacing: '0.04em' }}>REVIEW TYPE</span>
            {(['all', 'bugs', 'security', 'performance'] as ReviewType[]).map(t => {
              const labels: Record<ReviewType, string> = { all: 'All Issues', bugs: 'Bug Focus', security: 'Security', performance: 'Performance' }
              return (
                <button
                  key={t}
                  onClick={() => setReviewType(t)}
                  style={{
                    padding: '4px 12px', borderRadius: 6, fontSize: 12,
                    border: `1px solid ${reviewType === t ? 'var(--hairline-str)' : 'var(--hairline)'}`,
                    background: reviewType === t ? 'var(--surface-el)' : 'transparent',
                    color: reviewType === t ? 'var(--ink)' : 'var(--ink-ash)',
                    cursor: 'pointer', fontWeight: reviewType === t ? 600 : 400,
                  }}
                >
                  {labels[t]}
                </button>
              )
            })}
          </div>

          {/* 右栏内容区 */}
          {!isActive && !error && (
            <div className="flex flex-col items-center justify-center flex-1 text-center" style={{ minHeight: 400 }}>
              <div style={{ color: 'var(--ink-stone)', fontSize: 13 }}>
                粘贴 PR 链接，点击 Review 开始分析
              </div>
            </div>
          )}

          {isPending && !isStreaming && diffLines.length === 0 && (
            <div className="flex flex-col items-center mt-16 gap-3">
              <Spin size="large" />
              <p style={{ color: 'var(--ink-ash)', fontSize: 13 }}>正在获取 PR 数据...</p>
            </div>
          )}

          {showDiffPanel && (
            <DiffScannerPanel lines={diffLines} title={diffTitle} cursorPath={cursorPath} active />
          )}

          {isStreaming && streamText && !result && (
            <div className="mt-4">
              <div className="rounded-lg p-4 font-mono text-sm leading-relaxed whitespace-pre-wrap"
                style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}>
                {streamText}
                <span className="animate-pulse ml-0.5" style={{ color: '#6366f1' }}>▊</span>
              </div>
            </div>
          )}

          {result && (
            <ReviewResults
              result={result}
              prUrl={lastRef.current?.prUrl}
              githubToken={lastRef.current?.token}
            />
          )}

          {!isPending && !isStreaming && streamText && !result && !error && (
            <div className="mt-4">
              <div className="rounded-lg p-4 font-mono text-sm leading-relaxed whitespace-pre-wrap"
                style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}>
                {streamText}
              </div>
            </div>
          )}

          {error && (
            <div className="mt-6">
              <Alert message="Review 失败" description={error} type="error" showIcon className="mb-4"
                style={{ background: '#450a0a', borderColor: '#dc2626', color: '#fca5a5' }} />
              <Button onClick={reset}>清除错误，重新输入</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

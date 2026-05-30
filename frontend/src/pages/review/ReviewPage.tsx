import { useEffect, useRef } from 'react'
import { useReviewStream } from '../../hooks/useReviewStream'
import ReviewForm from '../../components/common/ReviewForm'
import ReviewResults from '../../components/common/ReviewResults'
import ReviewOptions from '../../components/common/ReviewOptions'
import DiffScannerPanel from '../../components/common/DiffScannerPanel'
import { useReviewOptions } from '../../stores/reviewOptions'
import type { Perspective } from '../../stores/reviewOptions'
import { Alert, Button, Spin, Typography } from 'antd'
import { GithubOutlined } from '@ant-design/icons'

const { Text } = Typography

export default function ReviewPage() {
  const { streamText, result, isStreaming, isPending, error, diffLines, diffTitle, cursorPath, startStream, reset } = useReviewStream()
  const { options } = useReviewOptions()
  const lastRef = useRef<{ prUrl: string; token?: string } | null>(null)
  const prevPerspective = useRef<Perspective>(options.perspective)

  // Re-submit when perspective changes and a PR was already submitted
  useEffect(() => {
    const prev = prevPerspective.current
    prevPerspective.current = options.perspective
    if (prev !== options.perspective && lastRef.current) {
      startStream(lastRef.current.prUrl, lastRef.current.token, options)
    }
  }, [options.perspective, startStream, options])

  const handleSubmit = (prUrl: string, githubToken?: string) => {
    lastRef.current = { prUrl, token: githubToken }
    startStream(prUrl, githubToken, options)
  }

  return (
    <div className="min-h-screen flex flex-col items-center p-4 sm:p-8" style={{ background: 'var(--canvas)' }}>
      <div className="flex flex-col items-center w-full max-w-2xl">
        <ReviewForm
          onSubmit={handleSubmit}
          loading={isPending || isStreaming}
        />
        <ReviewOptions />

        {/* Empty state */}
        {!streamText && !result && !isPending && !isStreaming && !error && (
          <div className="flex flex-col items-center mt-20 text-center">
            <GithubOutlined className="text-6xl text-gray-700 mb-6" />
            <Text className="text-gray-400 text-base max-w-md">
              粘贴 GitHub PR 链接，AI 自动分析代码变更、识别潜在问题、生成 Review 建议
            </Text>
            <Text className="text-gray-600 text-sm mt-4">
              示例：https://github.com/facebook/react/pull/123
            </Text>
          </div>
        )}

        {/* Connecting state — spinner before diff arrives */}
        {isPending && !isStreaming && diffLines.length === 0 && (
          <div className="flex flex-col items-center mt-16">
            <Spin size="large" />
            <p className="text-gray-500 mt-4">正在获取 PR 数据并分析...</p>
          </div>
        )}

        {/* Diff Scanner Panel — shows from diff arrival until result is ready */}
        {diffLines.length > 0 && !result && (
          <DiffScannerPanel lines={diffLines} title={diffTitle} cursorPath={cursorPath} active />
        )}

        {/* Streaming state — only show raw text when no diff panel */}
        {isStreaming && streamText && diffLines.length === 0 && (
          <div className="w-full max-w-2xl mt-8">
            <div
              className="rounded-lg p-4 font-mono text-sm leading-relaxed whitespace-pre-wrap"
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
            >
              {streamText}
              <span className="animate-pulse ml-0.5" style={{ color: '#6366f1' }}>▊</span>
            </div>
          </div>
        )}

        {/* Streaming complete, show raw text if JSON parse failed */}
        {!isPending && !isStreaming && streamText && !result && !error && (
          <div className="w-full max-w-2xl mt-8">
            <Text className="text-gray-400 text-sm block mb-2">分析完成（原始输出）：</Text>
            <div
              className="rounded-lg p-4 font-mono text-sm leading-relaxed whitespace-pre-wrap"
              style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
            >
              {streamText}
            </div>
          </div>
        )}

        {/* Structured result */}
        {result && <ReviewResults result={result} prUrl={lastRef.current?.prUrl} githubToken={lastRef.current?.token} />}

        {/* Error state */}
        {error && (
          <div className="mt-6 w-full max-w-2xl">
            <Alert
              message="Review 失败"
              description={error}
              type="error"
              showIcon
              className="mb-4"
              style={{ background: '#450a0a', borderColor: '#dc2626', color: '#fca5a5' }}
            />
            <Button onClick={reset}>清除错误，重新输入</Button>
          </div>
        )}
      </div>
    </div>
  )
}

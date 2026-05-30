import { useRef } from 'react'
import { useReviewStream } from '../../hooks/useReviewStream'
import ReviewForm from '../../components/common/ReviewForm'
import ReviewResults from '../../components/common/ReviewResults'
import DiffScannerPanel from '../../components/common/DiffScannerPanel'
import StreamingResults from '../../components/common/StreamingResults'
import { Alert, Button, Spin, Typography } from 'antd'
import { GithubOutlined } from '@ant-design/icons'

const { Text } = Typography

export default function ReviewPage() {
  const { streamText, partial, result, isStreaming, isPending, error, diffLines, diffTitle, cursorPath, startStream, reset } = useReviewStream()
  const lastRef = useRef<{ prUrl: string; token?: string } | null>(null)

  const handleSubmit = (prUrl: string, githubToken?: string) => {
    lastRef.current = { prUrl, token: githubToken }
    startStream(prUrl, githubToken)
  }

  // summary 一出现就切换到渐现模式，不再等 [DONE]
  const hasPartial = !!(partial?.summary)
  const showDiffPanel = diffLines.length > 0 && !hasPartial && !result

  return (
    <div className="min-h-screen flex flex-col items-center p-4 sm:p-8" style={{ background: 'var(--canvas)' }}>
      <div className="flex flex-col items-center w-full max-w-2xl">
        <ReviewForm
          onSubmit={handleSubmit}
          loading={isPending || isStreaming}
        />

        {/* Empty state — 提交后立即消失 */}
        {!streamText && !result && !isPending && !isStreaming && !error && diffLines.length === 0 && (
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

        {/* 获取 PR 数据中 */}
        {isPending && !isStreaming && diffLines.length === 0 && (
          <div className="flex flex-col items-center mt-16">
            <Spin size="large" />
            <p className="text-gray-500 mt-4">正在获取 PR 数据...</p>
          </div>
        )}

        {/* DiffScannerPanel — summary 出现前显示 */}
        {showDiffPanel && (
          <DiffScannerPanel
            lines={diffLines}
            title={diffTitle}
            cursorPath={cursorPath}
            active
            analyzing={isStreaming}
          />
        )}

        {/* 流式渐现结果 — summary 一到就渲染，issues 逐条填充，直到 result 完整到达 */}
        {hasPartial && !result && (
          <StreamingResults partial={partial!} isStreaming={isStreaming} />
        )}

        {/* 最终完整结果 */}
        {result && (
          <ReviewResults
            result={result}
            prUrl={lastRef.current?.prUrl}
            githubToken={lastRef.current?.token}
          />
        )}

        {/* JSON 解析失败降级 */}
        {!isPending && !isStreaming && streamText && !result && !hasPartial && !error && (
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

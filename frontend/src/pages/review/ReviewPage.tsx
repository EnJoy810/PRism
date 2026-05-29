import { useReview } from '../../hooks/useReview'
import ReviewForm from '../../components/common/ReviewForm'
import ReviewResults from '../../components/common/ReviewResults'
import { getApiErrorMessage } from '../../utils/error'
import { Alert, Button, Spin, Typography } from 'antd'
import { GithubOutlined } from '@ant-design/icons'

const { Text } = Typography

export default function ReviewPage() {
  const { mutate, data, isPending, error, reset } = useReview()

  return (
    <div className="min-h-screen bg-neutral-bg flex flex-col items-center p-8">
      <div className="flex flex-col items-center w-full max-w-2xl">
        <ReviewForm
          onSubmit={(prUrl, githubToken) => {
            reset()
            mutate({ pr_url: prUrl, github_token: githubToken })
          }}
          loading={isPending}
        />

        {/* Empty state */}
        {!data && !isPending && !error && (
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

        {/* Loading state */}
        {isPending && (
          <div className="flex flex-col items-center mt-16">
            <Spin size="large" />
            <p className="text-gray-500 mt-4">正在分析 PR，请稍候...</p>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="mt-6 w-full max-w-2xl">
            <Alert
              message="Review 失败"
              description={getApiErrorMessage(error)}
              type="error"
              showIcon
              className="mb-4"
              style={{ background: '#450a0a', borderColor: '#dc2626', color: '#fca5a5' }}
            />
            <Button onClick={() => reset()}>清除错误，重新输入</Button>
          </div>
        )}

        {/* Success state */}
        {data && <ReviewResults result={data} />}
      </div>
    </div>
  )
}

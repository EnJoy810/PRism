import { useReview } from '../../hooks/useReview'
import type { ReviewResult, Severity } from '../../types/review'
import ReviewForm from '../../components/common/ReviewForm'
import ReviewResults from '../../components/common/ReviewResults'
import { getApiErrorMessage } from '../../utils/error'
import { Alert, Spin } from 'antd'

export default function ReviewPage() {
  const { mutate, data, isPending, error } = useReview()

  return (
    <div className="min-h-screen bg-neutral-bg flex flex-col items-center p-8">
      <div className="flex flex-col items-center w-full max-w-2xl">
        <ReviewForm
          onSubmit={(prUrl, githubToken) => {
            mutate({ pr_url: prUrl, github_token: githubToken })
          }}
          loading={isPending}
        />

        {isPending && (
          <div className="flex flex-col items-center mt-16">
            <Spin size="large" />
            <p className="text-gray-500 mt-4">Analyzing PR...</p>
          </div>
        )}

        {error && (
          <Alert
            message="Review Failed"
            description={getApiErrorMessage(error)}
            type="error"
            showIcon
            className="mt-6 w-full max-w-2xl"
            style={{ background: '#450a0a', borderColor: '#dc2626', color: '#fca5a5' }}
          />
        )}

        {data && <ReviewResults result={data} />}
      </div>
    </div>
  )
}

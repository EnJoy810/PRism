import { useState } from 'react'
import { Button, Input, Typography } from 'antd'
import { GithubOutlined } from '@ant-design/icons'

const { Text } = Typography

const PR_URL_PATTERN = /github\.com\/[\w.-]+\/[\w.-]+\/pull\/\d+/

interface ReviewFormProps {
  onSubmit: (prUrl: string, githubToken?: string) => void
  loading: boolean
}

export default function ReviewForm({ onSubmit, loading }: ReviewFormProps) {
  const [prUrl, setPrUrl] = useState('')
  const [githubToken, setGithubToken] = useState('')

  const isValid = PR_URL_PATTERN.test(prUrl)

  const handleSubmit = () => {
    if (!isValid) return
    onSubmit(prUrl, githubToken || undefined)
  }

  return (
    <div className="w-full max-w-2xl">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-brand-primary flex items-center justify-center">
          <GithubOutlined className="text-white text-lg" />
        </div>
        <div>
          <Text strong className="text-gray-100 text-lg block">
            PRism
          </Text>
          <Text className="text-gray-500 text-sm">
            AI-Powered PR Review Assistant
          </Text>
        </div>
      </div>

      <div className="flex gap-2 mb-3">
        <Input
          placeholder="https://github.com/owner/repo/pull/123"
          value={prUrl}
          onChange={(e) => setPrUrl(e.target.value)}
          onPressEnter={handleSubmit}
          size="large"
          className="flex-1"
          status={prUrl && !isValid ? 'error' : undefined}
          style={{ background: '#1e293b', borderColor: '#334155', color: '#f1f5f9' }}
        />
        <Button
          type="primary"
          size="large"
          onClick={handleSubmit}
          disabled={!isValid}
          loading={loading}
          style={{ background: !isValid ? '#334155' : '#6366f1', borderColor: 'transparent' }}
        >
          Review
        </Button>
      </div>

      {prUrl && !isValid && (
        <Text className="text-red-400 text-sm block mb-2">
          Please enter a valid GitHub PR URL (e.g. https://github.com/owner/repo/pull/123)
        </Text>
      )}

      <Input.Password
        placeholder="GitHub Token (optional — increases API rate limits)"
        value={githubToken}
        onChange={(e) => setGithubToken(e.target.value)}
        size="small"
        className="w-full"
        style={{ background: '#1e293b', borderColor: '#334155', color: '#f1f5f9' }}
      />
    </div>
  )
}

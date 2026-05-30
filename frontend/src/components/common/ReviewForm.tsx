import { useState } from 'react'
import { Button, Input, Typography } from 'antd'

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
    <div className="w-full max-w-2xl pt-8 pb-2">
      <div className="flex items-center gap-3 mb-6">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center"
          style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)' }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="var(--ink-body)">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
          </svg>
        </div>
        <div>
          <Text strong style={{ color: 'var(--ink)', fontSize: 16, display: 'block', letterSpacing: '-0.01em' }}>
            PRism
          </Text>
          <Text style={{ color: 'var(--ink-ash)', fontSize: 13 }}>
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
        />
        <Button
          type="primary"
          size="large"
          onClick={handleSubmit}
          disabled={!isValid}
          loading={loading}
          style={{
            background: isValid ? 'var(--ink)' : 'var(--surface-el)',
            borderColor: 'transparent',
            color: isValid ? '#000' : 'var(--ink-stone)',
            fontWeight: 500,
            minWidth: 88,
          }}
        >
          Review
        </Button>
      </div>

      {prUrl && !isValid && (
        <Text style={{ color: 'var(--accent-red)', fontSize: 12, display: 'block', marginBottom: 8 }}>
          请输入有效的 GitHub PR 链接（如 https://github.com/owner/repo/pull/123）
        </Text>
      )}

      <Input.Password
        placeholder="GitHub Token（可选，提升 API 速率限制）"
        value={githubToken}
        onChange={(e) => setGithubToken(e.target.value)}
        size="small"
        className="w-full"
      />
    </div>
  )
}

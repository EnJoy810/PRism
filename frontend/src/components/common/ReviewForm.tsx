import { useState, useEffect, useRef } from 'react'

const PR_URL_PATTERN = /github\.com\/[\w.-]+\/[\w.-]+\/pull\/\d+/

interface ReviewFormProps {
  onFetchMeta: (prUrl: string, githubToken?: string) => void
  loading: boolean
  metaLoaded: boolean
}

function StepBadge({ n }: { n: number }) {
  return (
    <span
      style={{
        width: 22, height: 22, borderRadius: '50%',
        background: '#3b82f6',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 11, fontWeight: 700, color: '#fff', flexShrink: 0,
      }}
    >
      {n}
    </span>
  )
}

export default function ReviewForm({ onFetchMeta, loading, metaLoaded }: ReviewFormProps) {
  const [prUrl, setPrUrl] = useState('')
  const [githubToken, setGithubToken] = useState('')
  const [showToken, setShowToken] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const isValid = PR_URL_PATTERN.test(prUrl)

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (isValid && !metaLoaded && !loading) {
      timerRef.current = setTimeout(() => {
        onFetchMeta(prUrl, githubToken || undefined)
      }, 800)
    }
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prUrl, isValid])

  const handleSubmit = () => {
    if (!isValid || loading) return
    onFetchMeta(prUrl, githubToken || undefined)
  }

  return (
    <div
      className="rounded-xl p-5"
      style={{
        background: '#ffffff',
        border: '1px solid var(--hairline)',
        boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
      }}
    >
      {/* Step header */}
      <div className="flex items-center gap-2.5 mb-3">
        <StepBadge n={1} />
        <span style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>Pull Request</span>
      </div>

      <p style={{ fontSize: 13, color: '#64748b', marginBottom: 12, marginLeft: 0, lineHeight: 1.5 }}>
        Paste a PR link from GitHub, GitLab, Gitee or any Git platform.
      </p>

      {/* Input */}
      <div
        className="flex items-center gap-2 rounded-lg px-3"
        style={{
          background: '#ffffff',
          border: `1.5px solid ${prUrl && !isValid ? '#ef4444' : isValid ? '#86efac' : '#e2e8f0'}`,
          height: 40,
          boxShadow: isValid ? '0 0 0 3px rgba(16,185,129,0.10)' : 'none',
          transition: 'border-color 0.15s, box-shadow 0.15s',
        }}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="#94a3b8" style={{ flexShrink: 0 }}>
          <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
        </svg>
        <input
          value={prUrl}
          onChange={e => setPrUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSubmit()}
          placeholder="https://github.com/acme-inc/payment-service/pull/1287"
          style={{
            flex: 1, background: 'none', border: 'none', outline: 'none',
            color: '#0f172a', fontSize: 13,
          }}
        />
        {prUrl && (
          <button
            onClick={() => { setPrUrl('') }}
            style={{
              background: '#f1f5f9', border: 'none', cursor: 'pointer',
              color: '#94a3b8', padding: '1px 5px', borderRadius: 4, lineHeight: 1,
              fontSize: 14, fontWeight: 500,
            }}
          >
            ×
          </button>
        )}
      </div>

      {/* Status + button row */}
      <div className="flex items-center justify-between mt-3">
        <div style={{ fontSize: 12, minHeight: 18 }}>
          {loading && (
            <span style={{ color: '#64748b', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span
                style={{
                  width: 12, height: 12, border: '2px solid #e2e8f0',
                  borderTopColor: '#3b82f6', borderRadius: '50%',
                  display: 'inline-block', animation: 'spin 0.7s linear infinite',
                }}
              />
              Checking PR metadata…
            </span>
          )}
          {!loading && metaLoaded && (
            <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: 5 }}>
              <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0zm3.78 4.78a.75.75 0 0 0-1.06-1.06L6.75 8.69 5.28 7.22a.75.75 0 0 0-1.06 1.06l2 2a.75.75 0 0 0 1.06 0l4.5-4.5z"/>
              </svg>
              Link is valid and accessible
            </span>
          )}
          {!loading && prUrl && !isValid && (
            <span style={{ color: '#ef4444' }}>Invalid PR link format</span>
          )}
        </div>

        <button
          onClick={handleSubmit}
          disabled={!isValid || loading}
          style={{
            display: 'flex', alignItems: 'center', gap: 7,
            padding: '8px 18px', borderRadius: 8, fontSize: 13, fontWeight: 600,
            background: isValid && !loading
              ? 'linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%)'
              : '#f1f5f9',
            color: isValid && !loading ? '#ffffff' : '#94a3b8',
            border: 'none',
            cursor: isValid && !loading ? 'pointer' : 'not-allowed',
            boxShadow: isValid && !loading ? '0 2px 8px rgba(79,70,229,0.28)' : 'none',
            transition: 'all 0.15s',
          }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z"/>
          </svg>
          Start Review
        </button>
      </div>

      {/* Optional token */}
      <div className="mt-3" style={{ borderTop: '1px solid #f1f5f9', paddingTop: 10 }}>
        <button
          onClick={() => setShowToken(v => !v)}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#94a3b8', fontSize: 11, padding: 0,
            display: 'flex', alignItems: 'center', gap: 4,
          }}
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
            <path d={showToken ? 'M7 10l5 5 5-5z' : 'M10 17l5-5-5-5v10z'} />
          </svg>
          GitHub Token (optional, increases rate limit)
        </button>
        {showToken && (
          <input
            type="password"
            value={githubToken}
            onChange={e => setGithubToken(e.target.value)}
            placeholder="ghp_xxxxxxxxxxxx"
            style={{
              marginTop: 8, width: '100%',
              background: '#f8fafc', border: '1px solid #e2e8f0',
              borderRadius: 7, padding: '6px 10px',
              fontSize: 12, color: '#0f172a', outline: 'none',
            }}
          />
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

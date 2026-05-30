import { useRef, useState } from 'react'
import { useReviewStream } from '../../hooks/useReviewStream'
import ReviewForm from '../../components/common/ReviewForm'
import ReviewResults from '../../components/common/ReviewResults'
import DiffScannerPanel from '../../components/common/DiffScannerPanel'
import PRMetadataCard from '../../components/left/PRMetadataCard'
import ChangedFilesList from '../../components/left/ChangedFilesList'
import Navbar from '../../components/layout/Navbar'
import { Alert, Button, Spin } from 'antd'
import type { ReviewType, PRMeta } from '../../types/review'

const REVIEW_TYPES: { value: ReviewType; label: string }[] = [
  { value: 'all',         label: 'All (Bug, Security, Perf, Style)' },
  { value: 'bugs',        label: 'Bug Focus' },
  { value: 'security',    label: 'Security Only' },
  { value: 'performance', label: 'Performance' },
]

export default function ReviewPage() {
  const {
    streamText, result, isStreaming, isPending, error,
    diffLines, diffTitle, cursorPath, prMeta: streamMeta,
    startStream, reset,
  } = useReviewStream()

  const lastRef = useRef<{ prUrl: string; token?: string } | null>(null)
  const [reviewType, setReviewType] = useState<ReviewType>('all')
  const [syncedAt, setSyncedAt] = useState<number | null>(null)
  const [localMeta, setLocalMeta] = useState<PRMeta | null>(null)
  const [metaLoading, setMetaLoading] = useState(false)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [currentUrl, setCurrentUrl] = useState('')

  const displayMeta = streamMeta ?? localMeta

  const handleFetchMeta = async (prUrl: string, githubToken?: string) => {
    setCurrentUrl(prUrl)
    lastRef.current = { prUrl, token: githubToken }
    setMetaError(null)
    setMetaLoading(true)
    setLocalMeta(null)
    reset()
    try {
      const params = new URLSearchParams({ pr_url: prUrl })
      if (githubToken) params.set('github_token', githubToken)
      const resp = await fetch(`/api/pr/meta?${params}`)
      const body = await resp.json()
      if (body.code === '0') {
        setLocalMeta(body.data as PRMeta)
      } else {
        setMetaError(body.detail || 'Failed to fetch PR metadata')
      }
    } catch (e) {
      setMetaError((e as Error).message || 'Network error')
    } finally {
      setMetaLoading(false)
    }
  }

  const handleStartAIReview = () => {
    if (!lastRef.current) return
    setSyncedAt(Date.now())
    startStream(lastRef.current.prUrl, lastRef.current.token, reviewType)
  }

  const handleRerun = () => {
    if (!lastRef.current) return
    setSyncedAt(Date.now())
    startStream(lastRef.current.prUrl, lastRef.current.token, reviewType)
  }

  const metaLoaded = !!(localMeta || streamMeta)
  const showDiffPanel = diffLines.length > 0 && !result
  const isActive = isPending || isStreaming || !!result

  return (
    <div className="min-h-screen" style={{ background: '#f1f5f9' }}>
      <Navbar />

      <div
        className="flex gap-0"
        style={{ maxWidth: 1340, margin: '0 auto', minHeight: 'calc(100vh - 54px)' }}
      >
        {/* ── Left panel 42% ── */}
        <div
          className="flex flex-col p-6 gap-4"
          style={{
            width: '42%',
            borderRight: '1px solid #e2e8f0',
            minHeight: 'calc(100vh - 54px)',
          }}
        >
          <ReviewForm
            onFetchMeta={handleFetchMeta}
            loading={metaLoading}
            metaLoaded={metaLoaded && !metaLoading}
          />

          {metaError && !metaLoading && (
            <Alert
              message="Failed to fetch PR"
              description={metaError}
              type="error"
              showIcon
            />
          )}

          {displayMeta && currentUrl && (
            <PRMetadataCard meta={displayMeta} prUrl={currentUrl} />
          )}

          {displayMeta && displayMeta.files.length > 0 && (
            <ChangedFilesList files={displayMeta.files} />
          )}
        </div>

        {/* ── Right panel 58% ── */}
        <div className="flex flex-col p-6" style={{ width: '58%' }}>

          {/* Review Configuration card */}
          <div
            className="rounded-xl p-5 mb-5"
            style={{
              background: '#ffffff',
              border: '1px solid #e2e8f0',
              boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
            }}
          >
            <span style={{ fontSize: 14, fontWeight: 700, color: '#0f172a', display: 'block', marginBottom: 14 }}>
              Review Configuration
            </span>

            {/* Config columns */}
            <div className="grid grid-cols-4 gap-3 mb-4">
              {/* Review Type */}
              <div>
                <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600, marginBottom: 6, letterSpacing: '0.04em' }}>
                  Review Type
                </div>
                <div
                  style={{
                    background: '#f8fafc', border: '1px solid #e2e8f0',
                    borderRadius: 8, padding: '7px 10px',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="#4f46e5">
                    <path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/>
                  </svg>
                  <select
                    value={reviewType}
                    onChange={e => setReviewType(e.target.value as ReviewType)}
                    style={{
                      background: 'none', border: 'none', outline: 'none',
                      fontSize: 12, color: '#334155', cursor: 'pointer', flex: 1,
                    }}
                  >
                    {REVIEW_TYPES.map(t => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* AI Model */}
              <div>
                <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600, marginBottom: 6, letterSpacing: '0.04em' }}>
                  AI Model
                </div>
                <div
                  style={{
                    background: '#f8fafc', border: '1px solid #e2e8f0',
                    borderRadius: 8, padding: '7px 10px',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="#10b981">
                    <path d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zm-2 15l-5-5 1.4-1.4L10 14.2l7.6-7.6L19 8l-9 9z"/>
                  </svg>
                  <span style={{ fontSize: 12, color: '#334155' }}>DeepSeek (Latest)</span>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="#94a3b8" style={{ marginLeft: 'auto' }}>
                    <path d="M7 10l5 5 5-5z"/>
                  </svg>
                </div>
              </div>

              {/* Review Depth */}
              <div>
                <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600, marginBottom: 6, letterSpacing: '0.04em' }}>
                  Review Depth
                </div>
                <div
                  style={{
                    background: '#f8fafc', border: '1px solid #e2e8f0',
                    borderRadius: 8, padding: '7px 10px',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="#64748b">
                    <path d="M5 9.2h3V19H5zM10.6 5h2.8v14h-2.8zm5.6 8H19v6h-2.8z"/>
                  </svg>
                  <span style={{ fontSize: 12, color: '#334155' }}>Normal</span>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="#94a3b8" style={{ marginLeft: 'auto' }}>
                    <path d="M7 10l5 5 5-5z"/>
                  </svg>
                </div>
              </div>

              {/* Focus Areas */}
              <div>
                <div style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600, marginBottom: 6, letterSpacing: '0.04em' }}>
                  Focus Areas (Optional)
                </div>
                <div
                  style={{
                    background: '#f8fafc', border: '1px solid #e2e8f0',
                    borderRadius: 8, padding: '7px 10px',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <span style={{ fontSize: 12, color: '#94a3b8', flex: 1 }}>Select focus areas</span>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="#94a3b8">
                    <path d="M7 10l5 5 5-5z"/>
                  </svg>
                </div>
              </div>
            </div>

            {/* More Options + Start AI Review */}
            <div className="flex items-center justify-between">
              <button
                className="flex items-center gap-2"
                style={{
                  background: '#ffffff', border: '1px solid #e2e8f0',
                  borderRadius: 8, padding: '7px 14px', fontSize: 12,
                  color: '#475569', cursor: 'pointer', fontWeight: 500,
                  boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
                </svg>
                More Options
              </button>

              <button
                onClick={handleStartAIReview}
                disabled={!metaLoaded || isPending || isStreaming}
                className="flex items-center gap-2"
                style={{
                  padding: '9px 24px', borderRadius: 9, fontSize: 13, fontWeight: 700,
                  background: metaLoaded && !isPending && !isStreaming
                    ? 'linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%)'
                    : '#f1f5f9',
                  color: metaLoaded && !isPending && !isStreaming ? '#fff' : '#94a3b8',
                  border: 'none',
                  cursor: metaLoaded && !isPending && !isStreaming ? 'pointer' : 'not-allowed',
                  boxShadow: metaLoaded && !isPending && !isStreaming
                    ? '0 4px 14px rgba(79,70,229,0.35)' : 'none',
                  transition: 'all 0.15s',
                }}
              >
                {isPending || isStreaming ? (
                  <><Spin size="small" /> Analyzing…</>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/>
                    </svg>
                    Start AI Review
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Empty state */}
          {!isActive && !error && !metaError && (
            <div
              className="flex flex-col items-center justify-center flex-1 text-center"
              style={{ minHeight: 280 }}
            >
              <div
                style={{
                  width: 52, height: 52, borderRadius: 14,
                  background: '#ffffff', border: '1px solid #e2e8f0',
                  boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 14,
                }}
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="#94a3b8">
                  <path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/>
                </svg>
              </div>
              <p style={{ color: '#94a3b8', fontSize: 13, maxWidth: 260 }}>
                Paste a PR link on the left, then click{' '}
                <strong style={{ color: '#475569' }}>Start AI Review</strong> to begin
              </p>
            </div>
          )}

          {isPending && !isStreaming && diffLines.length === 0 && (
            <div className="flex flex-col items-center mt-10 gap-3">
              <Spin size="large" />
              <p style={{ color: '#64748b', fontSize: 13 }}>Fetching PR data…</p>
            </div>
          )}

          {showDiffPanel && (
            <DiffScannerPanel lines={diffLines} title={diffTitle} cursorPath={cursorPath} active />
          )}

          {isStreaming && streamText && !result && (
            <div className="mt-2 rounded-xl overflow-hidden" style={{ border: '1px solid #334155', boxShadow: '0 1px 4px rgba(0,0,0,0.1)' }}>
              <div className="px-4 py-2.5" style={{ background: '#1e293b', borderBottom: '1px solid #334155' }}>
                <span style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>AI Analysis</span>
              </div>
              <div
                className="p-4 font-mono text-sm leading-relaxed whitespace-pre-wrap"
                style={{ background: '#0f172a', color: '#e2e8f0' }}
              >
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
              onRerun={handleRerun}
              lastSyncedAt={syncedAt ?? undefined}
            />
          )}

          {!isPending && !isStreaming && streamText && !result && !error && (
            <div className="mt-2 rounded-xl overflow-hidden" style={{ border: '1px solid #334155' }}>
              <div className="p-4 font-mono text-sm leading-relaxed whitespace-pre-wrap"
                style={{ background: '#0f172a', color: '#e2e8f0' }}>
                {streamText}
              </div>
            </div>
          )}

          {error && (
            <div className="mt-4">
              <Alert message="Review Failed" description={error} type="error" showIcon className="mb-3" />
              <Button onClick={reset}>Clear and retry</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

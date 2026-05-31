import { useState } from 'react'
import PRUrlInput from '../../components/left/PRUrlInput'
import ChangedFilesList from '../../components/left/ChangedFilesList'
import ReviewResultsPanel from '../../components/right/ReviewResultsPanel'
import type { PRMeta } from '../../types/review'

export default function ReviewPage() {
  const [prUrl, setPrUrl] = useState<string | null>(null)
  const [meta, setMeta] = useState<PRMeta | null>(null)
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [githubToken, setGithubToken] = useState('')

  function handleMetaLoaded(data: unknown, url: string) {
    setMeta(data as PRMeta)
    setPrUrl(url)
    setSelectedFile(null)
  }

  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: '#F8F9FB',
        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          maxWidth: 1600,
          width: '100%',
          margin: '0 auto',
          padding: '28px 36px',
          display: 'grid',
          gridTemplateColumns: '320px 1fr',
          gap: 24,
          flex: 1,
          minHeight: 0,
        }}
      >
        {/* Left column — scrollable */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto', paddingBottom: 28 }}>
          <PRUrlInput
            onMetaLoaded={handleMetaLoaded}
            onTokenChange={setGithubToken}
            meta={meta}
            prUrl={prUrl}
          />

          {meta && (
            <div style={{ animation: 'fadeUp 0.25s ease-out' }}>
              <ChangedFilesList
                files={meta.files ?? []}
                selectedFile={selectedFile}
                onSelectFile={setSelectedFile}
              />
            </div>
          )}
        </div>

        {/* Right column — fixed height, panel fills it */}
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <ReviewResultsPanel
            prUrl={prUrl}
            meta={meta}
            githubToken={githubToken}
            onDiffLoaded={() => {}}
          />
        </div>
      </div>

      <style>{`
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.3; }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}

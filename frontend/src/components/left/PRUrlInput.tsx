import { useState, useEffect } from 'react'
import type { PRMeta } from '../../types/review'

const TOKEN_KEY = 'prism_github_token'

interface Props {
  onMetaLoaded: (meta: unknown, prUrl: string) => void
  onTokenChange?: (token: string) => void
  meta?: PRMeta | null
  prUrl?: string | null
}

function isValidPrUrl(url: string) {
  return /^https?:\/\/(github|gitlab|gitee)\.com\/.+\/.+\/(pull|merge_requests|pulls)\/\d+/.test(url.trim())
}

function timeAgo(iso: string): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const h = Math.floor(mins / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

export default function PRUrlInput({ onMetaLoaded, onTokenChange, meta, prUrl }: Props) {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? '')
  const [tokenVisible, setTokenVisible] = useState(false)
  const [tokenExpanded, setTokenExpanded] = useState(false)

  useEffect(() => {
    onTokenChange?.(token)
  }, [token, onTokenChange])

  function handleTokenChange(val: string) {
    setToken(val)
    localStorage.setItem(TOKEN_KEY, val)
  }

  const valid = isValidPrUrl(url)

  async function handleFetch() {
    if (!valid || loading) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`/api/pr/meta?pr_url=${encodeURIComponent(url.trim())}`)
      const json = await res.json()
      if (!res.ok || json.code !== '0') throw new Error(json.detail || '获取失败')
      onMetaLoaded(json.data, url.trim())
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '获取失败，请检查链接或网络')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ background: '#fff', border: '1px solid #E5E7EB', borderRadius: 12, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 20px 12px', borderBottom: '1px solid #F1F5F9' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{
            width: 22, height: 22, borderRadius: '50%',
            background: meta ? '#3b82f6' : '#2563EB',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, fontWeight: 700, color: '#fff', flexShrink: 0,
          }}>1</span>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>PR 链接</span>
        </div>
        {meta && (
          <span style={{
            background: '#ecfdf5', border: '1px solid #a7f3d0',
            color: '#059669', fontSize: 11, fontWeight: 700,
            padding: '2px 9px', borderRadius: 20,
          }}>就绪</span>
        )}
      </div>

      <div style={{ padding: '16px 20px' }}>
        {/* Input row */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          height: 38, padding: '0 12px',
          border: `1px solid ${error ? '#FCA5A5' : url && valid ? '#86EFAC' : '#E5E7EB'}`,
          borderRadius: 8, background: '#F8FAFC', transition: 'border-color 0.15s',
        }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="#94A3B8" style={{ flexShrink: 0 }}>
            <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
          </svg>
          <input
            value={url}
            onChange={e => { setUrl(e.target.value); setError('') }}
            onKeyDown={e => e.key === 'Enter' && handleFetch()}
            placeholder="https://github.com/owner/repo/pull/123"
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none',
              fontSize: 12, color: '#0F172A',
              fontFamily: "'JetBrains Mono', Consolas, monospace",
            }}
          />
          {url && (
            <button onClick={() => { setUrl(''); setError('') }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#94A3B8', lineHeight: 1 }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
            </button>
          )}
        </div>

        {/* Validation feedback */}
        <div style={{ minHeight: 18, marginTop: 5 }}>
          {error && <span style={{ fontSize: 11, color: '#EF4444', display: 'flex', alignItems: 'center', gap: 4 }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
            {error}
          </span>}
        </div>

        {/* Fetch button */}
        <button
          onClick={handleFetch}
          disabled={!valid || loading}
          style={{
            marginTop: 8, width: '100%', height: 36, borderRadius: 8, border: 'none',
            cursor: valid && !loading ? 'pointer' : 'not-allowed',
            background: valid && !loading ? 'linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%)' : '#F1F5F9',
            color: valid && !loading ? '#fff' : '#94A3B8',
            fontSize: 13, fontWeight: 600,
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
            transition: 'all 0.15s',
            boxShadow: valid && !loading ? '0 2px 8px rgba(37,99,235,0.28)' : 'none',
          }}
        >
          {loading ? (
            <>
              <span style={{ width: 12, height: 12, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />
              获取中…
            </>
          ) : (
            <>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              {meta ? '重新获取' : '开始获取'}
            </>
          )}
        </button>
      </div>

      {/* GitHub Token — collapsible */}
      <div style={{ borderTop: '1px solid #F1F5F9' }}>
        <button
          onClick={() => setTokenExpanded(e => !e)}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 20px', background: 'none', border: 'none',
            cursor: 'pointer', textAlign: 'left',
          }}
        >
          {token ? (
            <svg width="13" height="13" viewBox="0 0 24 24" fill="#059669"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/></svg>
          ) : (
            <svg width="13" height="13" viewBox="0 0 24 24" fill="#94A3B8"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM8.9 8V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2H8.9z"/></svg>
          )}
          <span style={{ fontSize: 12, fontWeight: 600, color: token ? '#059669' : '#64748B', flex: 1 }}>
            GitHub Token {token ? '· 已配置' : '· 未配置（生成评审需要）'}
          </span>
          <svg
            width="12" height="12" viewBox="0 0 24 24" fill="#94A3B8"
            style={{ transform: tokenExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}
          >
            <path d="M7 10l5 5 5-5z"/>
          </svg>
        </button>

        {tokenExpanded && (
          <div style={{ padding: '0 20px 16px' }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              height: 36, padding: '0 10px',
              border: '1px solid #E5E7EB', borderRadius: 8,
              background: '#F8FAFC',
            }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="#94A3B8" style={{ flexShrink: 0 }}>
                <path d="M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z"/>
              </svg>
              <input
                type={tokenVisible ? 'text' : 'password'}
                value={token}
                onChange={e => handleTokenChange(e.target.value)}
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                style={{
                  flex: 1, background: 'none', border: 'none', outline: 'none',
                  fontSize: 12, color: '#0F172A',
                  fontFamily: "'JetBrains Mono', Consolas, monospace",
                }}
              />
              <button
                onClick={() => setTokenVisible(v => !v)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#94A3B8', lineHeight: 1 }}
              >
                {tokenVisible
                  ? <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
                  : <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/></svg>
                }
              </button>
              {token && (
                <button
                  onClick={() => handleTokenChange('')}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#94A3B8', lineHeight: 1 }}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                </button>
              )}
            </div>
            <p style={{ fontSize: 11, color: '#94A3B8', margin: '6px 0 0', lineHeight: 1.5 }}>
              需要 <code style={{ background: '#F1F5F9', padding: '1px 4px', borderRadius: 3 }}>repo</code> 权限。Token 仅存储在本地浏览器中。
            </p>
          </div>
        )}
      </div>

      {/* PR Metadata — shown after fetch */}
      {meta && (
        <div style={{ borderTop: '1px solid #F1F5F9', padding: '16px 20px 20px' }}>
          {/* Title */}
          {meta.pr_title && (
            <a
              href={prUrl ?? '#'}
              target="_blank"
              rel="noreferrer"
              style={{ display: 'block', color: '#0F172A', fontSize: 14, fontWeight: 600, lineHeight: 1.5, textDecoration: 'none', marginBottom: 10 }}
              onMouseOver={e => { (e.currentTarget as HTMLAnchorElement).style.color = '#4f46e5' }}
              onMouseOut={e => { (e.currentTarget as HTMLAnchorElement).style.color = '#0F172A' }}
            >
              {meta.pr_title}
            </a>
          )}

          {/* Author + time */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            <img
              src={meta.author_avatar} alt={meta.author_name}
              style={{ width: 20, height: 20, borderRadius: '50%', background: '#e2e8f0' }}
              onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
            />
            <span style={{ fontSize: 12, fontWeight: 600, color: '#334155' }}>{meta.author_name}</span>
            {meta.created_at && <span style={{ fontSize: 12, color: '#94A3B8' }}>opened {timeAgo(meta.created_at)}</span>}
            {meta.updated_at && <span style={{ fontSize: 12, color: '#94A3B8' }}>· updated {timeAgo(meta.updated_at)}</span>}
          </div>

          {/* Branches */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <span style={{ fontSize: 11, fontWeight: 500, background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 5, padding: '3px 9px', color: '#2563eb', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {meta.head_branch}
            </span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="#94a3b8"><path d="M10 17l5-5-5-5v10z"/></svg>
            <span style={{ fontSize: 11, fontWeight: 500, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 5, padding: '3px 9px', color: '#64748b' }}>
              {meta.base_branch}
            </span>
          </div>

          {/* Stats — 2x2 grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              { label: '提交数',   value: String(meta.commits),       color: '#0f172a' },
              { label: '变更文件', value: String(meta.files_changed),  color: '#0f172a' },
              { label: '新增行',   value: `+${meta.additions}`,       color: '#059669' },
              { label: '删除行',   value: `−${meta.deletions}`,       color: '#dc2626' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ background: '#f8fafc', border: '1px solid #f1f5f9', borderRadius: 8, padding: '10px 14px' }}>
                <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>{label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

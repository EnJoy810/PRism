import { useState, useRef } from 'react'
import type { PRMeta, ReviewResult, Severity } from '../../types/review'
import { useSettings } from '../../stores/reviewOptions'
import SettingsDrawer from '../common/SettingsDrawer'
import ThinkingPanel from './ThinkingPanel'
import AISummaryCard from './AISummaryCard'
import RiskAnalysisCard from './RiskAnalysisCard'
import ReviewFindingsCard from './ReviewFindingsCard'
import MergeRecommendationCard from './MergeRecommendationCard'
import { parseDiffToMap, buildMarkdown } from './utils'

interface Props {
  prUrl: string | null
  meta: PRMeta | null
  githubToken?: string
  onDiffLoaded?: (diffMap: Map<string, string[]>) => void
}

type FilterTab = 'all' | Severity

const btnStyle: React.CSSProperties = {
  height: 30, padding: '0 12px', borderRadius: 6,
  border: '1px solid #E5E7EB', background: '#fff', color: '#374151',
  fontSize: 12, fontWeight: 500, cursor: 'pointer',
  display: 'flex', alignItems: 'center', gap: 5,
}

export default function ReviewResultsPanel({ prUrl, meta, githubToken, onDiffLoaded }: Props) {
  const { model, apiKey, baseUrl } = useSettings()
  const [result, setResult] = useState<ReviewResult | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [thinkText, setThinkText] = useState('')
  const [thinkDone, setThinkDone] = useState(false)
  const [thinkCollapsed, setThinkCollapsed] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [filterTab, setFilterTab] = useState<FilterTab>('all')
  const [streamError, setStreamError] = useState('')
  const [postLoading, setPostLoading] = useState(false)
  const [postMsg, setPostMsg] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const thinkRef = useRef<HTMLDivElement>(null)

  function handleViewInPR() {
    if (prUrl) window.open(prUrl, '_blank', 'noopener,noreferrer')
  }

  function handleExport() {
    if (!result || !prUrl) return
    const md = buildMarkdown(result, prUrl, meta)
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `pr-review-${Date.now()}.md`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  async function handlePostReview() {
    if (!result || !prUrl || !githubToken || postLoading) return
    setPostLoading(true)
    setPostMsg('')
    try {
      const res = await fetch('/api/review/post', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pr_url: prUrl,
          github_token: githubToken,
          result: { summary: result.summary, risk_level: result.risk_level, issues: result.issues, stats: result.stats },
        }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== '0') throw new Error(json.detail || '提交失败')
      setPostMsg('评审已提交到 GitHub ✓')
      if (json.data?.html_url) window.open(json.data.html_url, '_blank', 'noopener,noreferrer')
    } catch (e: unknown) {
      setPostMsg((e as Error).message || '提交失败，请重试')
    } finally {
      setPostLoading(false)
    }
  }

  async function startReview() {
    if (!prUrl || !meta || streaming) return
    if (!apiKey) {
      setStreamError('请在设置中配置 API Key')
      return
    }
    if (!githubToken) {
      setStreamError('请填写 GitHub Token')
      return
    }
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setStreaming(true)
    setResult(null)
    setThinkText('')
    setThinkDone(false)
    setThinkCollapsed(false)
    setStreamError('')
    setFilterTab('all')

    try {
      const res = await fetch('/api/review/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pr_url: prUrl,
          model: model || 'deepseek-v4-flash',
          api_key: apiKey || undefined,
          github_token: githubToken || undefined,
        }),
        signal: ctrl.signal,
      })
      if (!res.ok) throw new Error(`请求失败: ${res.status}`)

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let resultAccumulated = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() ?? ''

        for (const part of parts) {
          const line = part.trim()
          if (!line.startsWith('data:')) continue
          const raw = line.slice(5).trim()

          if (raw === '[DONE]') {
            try {
              let jsonStr = resultAccumulated.trim()
              const fenceMatch = jsonStr.match(/```(?:json)?\s*([\s\S]*?)```/)
              if (fenceMatch) {
                jsonStr = fenceMatch[1].trim()
              } else {
                const start = jsonStr.indexOf('{')
                const end = jsonStr.lastIndexOf('}')
                if (start !== -1 && end > start) jsonStr = jsonStr.slice(start, end + 1)
              }
              const parsed = JSON.parse(jsonStr) as ReviewResult
              setResult(parsed)
              setThinkDone(true)
              setTimeout(() => setThinkCollapsed(true), 600)
            } catch {
              setStreamError('结果解析失败，请重试')
            }
            setStreaming(false)
            return
          }

          try {
            const evt = JSON.parse(raw)
            if (evt.type === 'diff' && evt.lines && onDiffLoaded) {
              onDiffLoaded(parseDiffToMap(evt.lines as string[]))
            } else if (evt.type === 'thinking') {
              setThinkText(t => t + evt.delta)
              setTimeout(() => {
                if (thinkRef.current) thinkRef.current.scrollTop = thinkRef.current.scrollHeight
              }, 0)
            } else if (evt.type === 'result') {
              resultAccumulated += evt.delta
              setThinkDone(true)
            }
          } catch { /* skip */ }
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name !== 'AbortError') {
        setStreamError((e as Error).message || '分析失败，请重试')
      }
      setStreaming(false)
    }
  }

  const canStart = !!prUrl && !!meta && !streaming && !!apiKey && !!githubToken
  const allIssues = result?.issues ?? []

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{
        flex: 1, background: '#fff', border: '1px solid #E5E7EB',
        borderRadius: 12, boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0,
      }}>
        {/* Header */}
        <div style={{
          borderBottom: '1px solid #F1F5F9', padding: '12px 20px',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>AI Code Review</span>
            <SettingsDrawer />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {result && (
              <>
                <button onClick={handleViewInPR} style={btnStyle} title="在 GitHub 中查看 PR">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/></svg>
                  在 PR 中查看
                </button>
                <button onClick={handleExport} style={btnStyle} title="导出 Markdown 报告">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
                  导出报告
                </button>
                <button
                  onClick={handlePostReview}
                  disabled={!githubToken || postLoading}
                  title={!githubToken ? '需要配置 GitHub Token' : '提交评审到 GitHub'}
                  style={{
                    ...btnStyle,
                    opacity: !githubToken ? 0.5 : 1,
                    cursor: !githubToken || postLoading ? 'not-allowed' : 'pointer',
                    color: postMsg.includes('✓') ? '#059669' : '#374151',
                  }}
                >
                  {postLoading
                    ? <span style={{ width: 10, height: 10, border: '2px solid #E5E7EB', borderTopColor: '#374151', borderRadius: '50%', animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />
                    : <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
                  }
                  {postMsg || (postLoading ? '提交中…' : '生成评审')}
                </button>
              </>
            )}
            <button
              onClick={startReview}
              disabled={!canStart}
              title={!prUrl || !meta ? '请先填写 PR 链接' : !apiKey ? '请在设置中配置 API Key' : !githubToken ? '请填写 GitHub Token' : ''}
              style={{
                height: 34, padding: '0 16px', borderRadius: 8, border: 'none',
                cursor: canStart ? 'pointer' : 'not-allowed',
                background: canStart ? 'linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%)' : '#F1F5F9',
                color: canStart ? '#fff' : '#94A3B8',
                fontSize: 13, fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 7,
                boxShadow: canStart ? '0 2px 8px rgba(37,99,235,0.28)' : 'none',
                transition: 'all 0.15s',
              }}
            >
              {streaming ? (
                <>
                  <span style={{ width: 12, height: 12, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />
                  分析中…
                </>
              ) : (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/></svg>
                  开始 AI 审查
                </>
              )}
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        <div style={{
          flex: 1, overflowY: 'auto', padding: '16px 20px',
          display: 'flex', flexDirection: 'column', gap: 16, minHeight: 0,
        }}>
          {streaming && !thinkText && !thinkDone && (
            <div style={{ background: '#fff', border: '1px solid #E5E7EB', borderRadius: 10, padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0, background: '#8B5CF6', animation: 'pulse 1.2s ease-in-out infinite' }} />
              <span style={{ fontSize: 12, color: '#6D28D9', fontWeight: 600 }}>正在连接模型…</span>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6, marginLeft: 8 }}>
                {[100, 80, 60].map((w, i) => (
                  <div key={i} style={{ height: 10, borderRadius: 4, background: '#E9D5FF', width: `${w}%`, animation: `pulse ${1.2 + i * 0.2}s ease-in-out infinite` }} />
                ))}
              </div>
            </div>
          )}

          {(streaming || thinkDone) && thinkText && (
            <ThinkingPanel
              thinkText={thinkText}
              streaming={streaming}
              thinkDone={thinkDone}
              thinkCollapsed={thinkCollapsed}
              setThinkCollapsed={setThinkCollapsed}
              thinkRef={thinkRef}
            />
          )}

          {result && <AISummaryCard result={result} meta={meta} />}

          {result && result.risk_areas && result.risk_areas.length > 0 && (
            <RiskAnalysisCard riskAreas={result.risk_areas} />
          )}

          {result && allIssues.length > 0 && (
            <ReviewFindingsCard
              issues={allIssues}
              filterTab={filterTab}
              setFilterTab={setFilterTab}
              expandedId={expandedId}
              setExpandedId={setExpandedId}
            />
          )}

          {result && result.merge_recommendation && (
            <MergeRecommendationCard rec={result.merge_recommendation} />
          )}

          {!streaming && !result && !streamError && (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
              <div style={{ textAlign: 'center' }}>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="#CBD5E1" style={{ margin: '0 auto 10px', display: 'block' }}>
                  <path d="M20 8h-2.81c-.45-.78-1.07-1.45-1.82-1.96L17 4.41 15.59 3l-2.17 2.17C12.96 5.06 12.49 5 12 5c-.49 0-.96.06-1.41.17L8.41 3 7 4.41l1.62 1.63C7.88 6.55 7.26 7.22 6.81 8H4v2h2.09c-.05.33-.09.66-.09 1v1H4v2h2v1c0 .34.04.67.09 1H4v2h2.81c1.04 1.79 2.97 3 5.19 3s4.15-1.21 5.19-3H20v-2h-2.09c.05-.33.09-.66.09-1v-1h2v-2h-2v-1c0-.34-.04-.67-.09-1H20V8z"/>
                </svg>
                <p style={{ color: '#94A3B8', fontSize: 13 }}>
                  {meta ? '点击"开始 AI 审查"开始分析' : '粘贴 PR 链接以开始审查'}
                </p>
              </div>
            </div>
          )}

          {streamError && (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 200 }}>
              <div style={{ textAlign: 'center' }}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="#FCA5A5" style={{ margin: '0 auto 10px', display: 'block' }}>
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                </svg>
                <p style={{ color: '#EF4444', fontSize: 13 }}>{streamError}</p>
                <button onClick={startReview} style={{ marginTop: 10, fontSize: 12, color: '#2563EB', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
                  重试
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

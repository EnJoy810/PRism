import { useState, useRef, useCallback } from 'react'
import type { ReviewResult, ReviewIssue, WalkthroughEntry } from '../types/review'

interface PartialResult {
  summary?: string
  risk_level?: 'HIGH' | 'MEDIUM' | 'LOW'
  walkthrough?: WalkthroughEntry[]
  issues?: ReviewIssue[]
}

// 从流式累积文本中增量提取已完整输出的字段
function extractPartial(text: string): PartialResult | null {
  const partial: PartialResult = {}

  const summaryMatch = text.match(/"summary"\s*:\s*"((?:[^"\\]|\\.)*)"/)
  if (summaryMatch) partial.summary = summaryMatch[1].replace(/\\n/g, '\n').replace(/\\"/g, '"')

  const riskMatch = text.match(/"risk_level"\s*:\s*"(HIGH|MEDIUM|LOW)"/)
  if (riskMatch) partial.risk_level = riskMatch[1] as 'HIGH' | 'MEDIUM' | 'LOW'

  // 提取已完整出现的 walkthrough 数组
  const wtSection = text.match(/"walkthrough"\s*:\s*\[([^\]]*)\]/)
  if (wtSection) {
    try { partial.walkthrough = JSON.parse(`[${wtSection[1]}]`) } catch { /* 尚不完整 */ }
  }

  // 逐个提取已完整出现的 issue 对象（花括号配对）
  const issuesStart = text.indexOf('"issues"')
  if (issuesStart !== -1) {
    const arrStart = text.indexOf('[', issuesStart)
    if (arrStart !== -1) {
      const issues: ReviewIssue[] = []
      let depth = 0, objStart = -1
      for (let i = arrStart + 1; i < text.length; i++) {
        const c = text[i]
        if (c === '{') { if (depth === 0) objStart = i; depth++ }
        else if (c === '}') {
          depth--
          if (depth === 0 && objStart !== -1) {
            try { issues.push(JSON.parse(text.slice(objStart, i + 1))) } catch { /* skip */ }
            objStart = -1
          }
        }
      }
      if (issues.length > 0) partial.issues = issues
    }
  }

  return Object.keys(partial).length > 0 ? partial : null
}

interface UseReviewStreamReturn {
  streamText: string
  partial: PartialResult | null
  result: ReviewResult | null
  isStreaming: boolean
  isPending: boolean
  error: string | null
  diffLines: string[]
  diffTitle: string
  cursorPath: number[]
  startStream: (prUrl: string, githubToken?: string) => void
  reset: () => void
}

export function useReviewStream(): UseReviewStreamReturn {
  const [streamText, setStreamText] = useState('')
  const [partial, setPartial] = useState<PartialResult | null>(null)
  const [result, setResult] = useState<ReviewResult | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isPending, setIsPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [diffLines, setDiffLines] = useState<string[]>([])
  const [diffTitle, setDiffTitle] = useState('')
  const [cursorPath, setCursorPath] = useState<number[]>([])
  const abortRef = useRef<AbortController | null>(null)

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setStreamText('')
    setPartial(null)
    setResult(null)
    setIsStreaming(false)
    setIsPending(false)
    setError(null)
    setDiffLines([])
    setDiffTitle('')
    setCursorPath([])
  }, [])

  const startStream = useCallback(async (prUrl: string, githubToken?: string) => {
    reset()
    setIsPending(true)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const response = await fetch('/api/review/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pr_url: prUrl, github_token: githubToken }),
        signal: controller.signal,
      })

      if (!response.ok) {
        const body = await response.text()
        setError(body || `HTTP ${response.status}`)
        setIsPending(false)
        return
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''
      let hasFirstChunk = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n')
        buffer = parts.pop() || ''

        for (const line of parts) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data: ')) continue

          const payload = trimmed.slice(6)
          if (payload === '[DONE]') {
            const cleaned = accumulated.replace(/```json\s*/g, '').replace(/```\s*/g, '').trim()
            try {
              const parsed = JSON.parse(cleaned)
              const issues: ReviewIssue[] = parsed.issues ?? []
              setResult({
                pr_url: '',
                summary: parsed.summary ?? '',
                risk_level: parsed.risk_level ?? 'LOW',
                walkthrough: parsed.walkthrough ?? [],
                issues,
                stats: {
                  files_changed: 0,
                  additions: 0,
                  deletions: 0,
                  issues_by_severity: {
                    ERROR: issues.filter(i => i.severity === 'ERROR').length,
                    WARNING: issues.filter(i => i.severity === 'WARNING').length,
                    INFO: issues.filter(i => i.severity === 'INFO').length,
                  },
                },
              })
            } catch {
              setResult(null)
            }
            setIsStreaming(false)
            setIsPending(false)
            return
          }

          try {
            const parsed = JSON.parse(payload)
            if (parsed.type === 'diff' && Array.isArray(parsed.lines)) {
              setDiffLines(parsed.lines)
              setDiffTitle(parsed.title ?? '')
              setIsPending(false)
              continue
            }
            if (parsed.type === 'cursor_path' && Array.isArray(parsed.cursor_path)) {
              setCursorPath(parsed.cursor_path)
              continue
            }
            if (typeof parsed.delta === 'string') {
              accumulated += parsed.delta
              setStreamText(accumulated)
              if (!hasFirstChunk) {
                hasFirstChunk = true
                setIsPending(false)
                setIsStreaming(true)
              }
              // 增量解析：每隔若干 delta 尝试提取已完整字段
              const p = extractPartial(accumulated)
              if (p) setPartial(p)
            }
          } catch {
            // skip malformed chunks
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      setError((err as Error).message || '流式请求失败')
    } finally {
      setIsStreaming(false)
      setIsPending(false)
    }
  }, [reset])

  return { streamText, partial, result, isStreaming, isPending, error, diffLines, diffTitle, cursorPath, startStream, reset }
}

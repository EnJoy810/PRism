import { useState, useRef, useCallback } from 'react'
import type { ReviewResult } from '../types/review'

interface StreamOptions {
  includeStyle?: boolean
  contextLines?: number
}

interface UseReviewStreamReturn {
  streamText: string
  result: ReviewResult | null
  isStreaming: boolean
  isPending: boolean
  error: string | null
  diffLines: string[]
  diffTitle: string
  startStream: (prUrl: string, githubToken?: string, options?: StreamOptions) => void
  reset: () => void
}

export function useReviewStream(): UseReviewStreamReturn {
  const [streamText, setStreamText] = useState('')
  const [result, setResult] = useState<ReviewResult | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isPending, setIsPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [diffLines, setDiffLines] = useState<string[]>([])
  const [diffTitle, setDiffTitle] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setStreamText('')
    setResult(null)
    setIsStreaming(false)
    setIsPending(false)
    setError(null)
    setDiffLines([])
    setDiffTitle('')
  }, [])

  const startStream = useCallback(async (prUrl: string, githubToken?: string, options?: StreamOptions) => {
    reset()
    setIsPending(true)

    const controller = new AbortController()
    abortRef.current = controller

    const body = {
      pr_url: prUrl,
      github_token: githubToken,
      options: {
        include_style: options?.includeStyle ?? false,
        context_lines: options?.contextLines ?? 3,
      },
    }

    try {
      const response = await fetch('/api/review/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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
            const cleaned = accumulated
              .replace(/```json\s*/g, '')
              .replace(/```\s*/g, '')
              .trim()
            try {
              const parsed = JSON.parse(cleaned)
              setResult(parsed)
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
            if (typeof parsed.delta === 'string') {
              accumulated += parsed.delta
              setStreamText(accumulated)
              if (!hasFirstChunk) {
                hasFirstChunk = true
                setIsPending(false)
                setIsStreaming(true)
                setDiffLines([])
              }
            }
          } catch {
            // skip malformed JSON chunks
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

  return { streamText, result, isStreaming, isPending, error, diffLines, diffTitle, startStream, reset }
}

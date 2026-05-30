import { useRef, useEffect, useState } from 'react'

type LineKind = 'add' | 'del' | 'meta' | 'ctx'

function classifyLine(line: string): LineKind {
  if (line.startsWith('+++') || line.startsWith('---')) return 'meta'
  if (line.startsWith('@@')) return 'meta'
  if (line.startsWith('+')) return 'add'
  if (line.startsWith('-')) return 'del'
  return 'ctx'
}

interface DiffScannerPanelProps {
  lines: string[]
  title: string
  cursorPath: number[]
  active: boolean
}

const LINE_HEIGHT = 20
const LINE_NUM_WIDTH = 44
const CHAR_WIDTH = 7.5
const SCAN_INTERVAL_MS = 120

const lineColors: Record<LineKind, { bg: string; color: string }> = {
  add: { bg: 'rgba(40, 120, 40, 0.25)', color: '#b5cea8' },
  del: { bg: 'rgba(120, 40, 40, 0.25)', color: '#f44747' },
  meta: { bg: 'rgba(0, 100, 200, 0.15)', color: '#569cd6' },
  ctx: { bg: 'transparent', color: '#d4d4d4' },
}

function getCursorX(line: string): number {
  const content = line.slice(1)
  const targetChar = Math.min(content.trimEnd().length, 60)
  return LINE_NUM_WIDTH + 12 + targetChar * CHAR_WIDTH
}

export default function DiffScannerPanel({ lines, title, cursorPath, active }: DiffScannerPanelProps) {
  const [pathIndex, setPathIndex] = useState(0)
  const [visible, setVisible] = useState(false)
  const [done, setDone] = useState(false)
  const lineRefs = useRef<(HTMLDivElement | null)[]>([])
  const skipRef = useRef(false)

  useEffect(() => {
    if (active) {
      requestAnimationFrame(() => setVisible(true))
    } else {
      const timer = setTimeout(() => setVisible(false), 200)
      return () => clearTimeout(timer)
    }
  }, [active])

  const path = cursorPath.length > 0 ? cursorPath : lines.map((_, i) => i + 1)

  useEffect(() => {
    if (!active || lines.length === 0) return

    setPathIndex(0)
    setDone(false)
    skipRef.current = false

    const interval = setInterval(() => {
      setPathIndex((prev) => {
        if (prev >= path.length - 1) {
          setDone(true)
          return prev
        }
        const lineIdx = path[prev] - 1
        const line = lines[lineIdx] ?? ''
        const kind = classifyLine(line)

        if ((kind === 'add' || kind === 'del') && !skipRef.current) {
          skipRef.current = true
          return prev
        }
        skipRef.current = false

        return prev + 1
      })
    }, SCAN_INTERVAL_MS)

    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, lines.length, path])

  useEffect(() => {
    const lineIdx = path[pathIndex]
    if (!lineIdx) return
    const el = lineRefs.current[lineIdx - 1]
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [pathIndex, path])

  if (!visible) return null

  const lineIdx = path[pathIndex] ?? 1
  const cursorTop = (lineIdx - 1) * LINE_HEIGHT + 6
  const cursorLeft = getCursorX(lines[lineIdx - 1] ?? '')

  return (
    <div
      className="w-full max-w-2xl mt-8 overflow-hidden"
      style={{
        borderRadius: 8,
        border: '1px solid #333333',
        opacity: active ? 1 : 0,
        transform: active ? 'translateY(0)' : 'translateY(-8px)',
        transition: 'opacity 150ms ease-in, transform 150ms ease-in',
      }}
    >
      {/* Tab bar */}
      <div
        className="flex items-center gap-2 px-3 select-none"
        style={{ height: 32, background: '#252526', borderBottom: '1px solid #333' }}
      >
        {['#ff5f57', '#febc2e', '#28c840'].map((c) => (
          <span key={c} style={{ width: 12, height: 12, borderRadius: '50%', background: c }} />
        ))}
        <span className="ml-2 text-xs truncate" style={{ color: '#ccc' }}>
          CHANGES &nbsp;—&nbsp; {title.slice(0, 40)}{title.length > 40 ? '...' : ''}
        </span>
      </div>

      {/* Status bar */}
      <div
        className="flex items-center gap-1.5 px-3 text-xs select-none"
        style={{ height: 24, background: '#007acc', color: '#fff' }}
      >
        {done ? (
          <>
            <span className="font-bold">✓</span>
            <span>AI Agent · Diff scan complete</span>
          </>
        ) : cursorPath.length > 0 ? (
          <>
            <span className="animate-pulse font-bold">▌</span>
            <span>AI Agent · Reading diff ({pathIndex + 1}/{path.length})</span>
          </>
        ) : (
          <>
            <span className="animate-pulse font-bold">▌</span>
            <span>AI Agent · Reading diff...</span>
          </>
        )}
      </div>

      {/* Code area */}
      <div
        style={{
          position: 'relative',
          height: 280,
          overflow: 'hidden',
          background: '#1e1e1e',
          fontFamily: "'JetBrains Mono','Fira Code','Cascadia Code',Consolas,monospace",
          fontSize: 12.5,
          lineHeight: `${LINE_HEIGHT}px`,
        }}
      >
        {/* Cursor SVG */}
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          style={{
            position: 'absolute',
            top: cursorTop,
            left: cursorLeft,
            pointerEvents: 'none',
            zIndex: 10,
            filter: 'drop-shadow(1px 2px 3px rgba(0,0,0,0.6))',
            transition: 'top 180ms cubic-bezier(0.22, 1, 0.36, 1), left 120ms cubic-bezier(0.22, 1, 0.36, 1)',
          }}
        >
          <path
            d="M4 2 L4 16 L7.5 12.5 L10.5 18 L12.5 17 L9.5 11 L14 11 Z"
            fill="white"
            stroke="black"
            strokeWidth="1"
          />
        </svg>

        {/* Lines */}
        {lines.map((line, i) => {
          const kind = classifyLine(line)
          const colors = lineColors[kind]
          const isCurrent = i === lineIdx - 1

          return (
            <div
              key={i}
              ref={(el) => { lineRefs.current[i] = el }}
              className="flex"
              style={{
                height: LINE_HEIGHT,
                background: isCurrent ? 'rgba(255,255,255,0.04)' : colors.bg,
              }}
            >
              <div
                className="shrink-0 text-right select-none"
                style={{
                  width: LINE_NUM_WIDTH,
                  paddingRight: 8,
                  color: isCurrent ? '#ccc' : '#858585',
                  borderRight: '1px solid #333',
                }}
              >
                {i + 1}
              </div>
              <span className="pl-2 truncate" style={{ color: colors.color }}>
                {line}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

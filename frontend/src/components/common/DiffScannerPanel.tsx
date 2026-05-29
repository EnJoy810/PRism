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
  active: boolean
}

const SCAN_INTERVAL_MS = 110

const lineColors: Record<LineKind, { bg: string; color: string }> = {
  add: { bg: 'rgba(40, 120, 40, 0.25)', color: '#b5cea8' },
  del: { bg: 'rgba(120, 40, 40, 0.25)', color: '#f44747' },
  meta: { bg: 'rgba(0, 100, 200, 0.15)', color: '#569cd6' },
  ctx: { bg: 'transparent', color: '#d4d4d4' },
}

export default function DiffScannerPanel({ lines, title, active }: DiffScannerPanelProps) {
  const [currentLine, setCurrentLine] = useState(0)
  const [visible, setVisible] = useState(false)
  const lineRefs = useRef<(HTMLDivElement | null)[]>([])
  const linesRef = useRef(lines)
  const pauseRef = useRef(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  linesRef.current = lines

  const scrollContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (active) {
      requestAnimationFrame(() => setVisible(true))
    } else {
      const timer = setTimeout(() => setVisible(false), 150)
      return () => clearTimeout(timer)
    }
  }, [active])

  useEffect(() => {
    if (!active || lines.length === 0) return

    setCurrentLine(0)
    pauseRef.current = 0

    intervalRef.current = setInterval(() => {
      setCurrentLine((prev) => {
        const kind = classifyLine(linesRef.current[prev] ?? '')
        if ((kind === 'add' || kind === 'del') && pauseRef.current < 1) {
          pauseRef.current += 1
          return prev
        }
        pauseRef.current = 0
        return (prev + 1) % linesRef.current.length
      })
    }, SCAN_INTERVAL_MS)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [active, lines.length])

  useEffect(() => {
    if (!active) return
    const el = lineRefs.current[currentLine]
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [currentLine, active])

  if (!visible) return null

  return (
    <div
      className="w-full max-w-2xl mt-8 overflow-hidden transition-all duration-200"
      style={{
        opacity: active ? 1 : 0,
        transform: active ? 'translateY(0)' : 'translateY(-8px)',
        borderRadius: 8,
        border: '1px solid #333333',
      }}
    >
      {/* Tab bar */}
      <div
        className="flex items-center gap-2 px-3"
        style={{ height: 32, background: '#252526', borderBottom: '1px solid #333333' }}
      >
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff5f57' }} />
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#febc2e' }} />
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#28c840' }} />
        <span className="ml-2 text-xs truncate" style={{ color: '#cccccc' }}>
          CHANGES &nbsp;—&nbsp; {title}
        </span>
      </div>

      {/* Status bar */}
      <div
        className="flex items-center gap-2 px-3 text-xs"
        style={{ height: 24, background: '#007acc', color: '#ffffff' }}
      >
        <span className="animate-pulse">●</span>
        AI 正在审查代码...
      </div>

      {/* Code area */}
      <div
        ref={scrollContainerRef}
        style={{
          height: 280,
          overflow: 'hidden',
          background: '#1e1e1e',
          fontFamily: "'JetBrains Mono','Fira Code','Cascadia Code',Consolas,monospace",
          fontSize: 12.5,
          lineHeight: '20px',
        }}
      >
        {lines.map((line, i) => {
          const kind = classifyLine(line)
          const colors = lineColors[kind]
          const isCurrent = i === currentLine

          return (
            <div
              key={i}
              ref={(el) => { lineRefs.current[i] = el }}
              className="flex"
              style={{
                background: isCurrent ? 'rgba(255,255,255,0.07)' : colors.bg,
                borderLeft: isCurrent ? '2px solid rgba(255,255,255,0.5)' : '2px solid transparent',
              }}
            >
              {/* Line number */}
              <div
                className="shrink-0 text-right select-none"
                style={{
                  width: 44,
                  paddingRight: 8,
                  color: isCurrent ? '#cccccc' : '#858585',
                  borderRight: '1px solid #333333',
                  marginRight: 12,
                }}
              >
                {i + 1}
              </div>
              {/* Line content */}
              <span style={{ color: colors.color, whiteSpace: 'pre' }}>{line}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

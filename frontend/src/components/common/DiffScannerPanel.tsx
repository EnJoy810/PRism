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

const LINE_HEIGHT = 20
const VISIBLE_LINES = 14
const CODE_HEIGHT = LINE_HEIGHT * VISIBLE_LINES

const lineColors: Record<LineKind, { bg: string; color: string }> = {
  add: { bg: 'rgba(40, 120, 40, 0.25)', color: '#b5cea8' },
  del: { bg: 'rgba(120, 40, 40, 0.25)', color: '#f44747' },
  meta: { bg: 'rgba(0, 100, 200, 0.15)', color: '#569cd6' },
  ctx: { bg: 'transparent', color: '#d4d4d4' },
}

export default function DiffScannerPanel({ lines, title, active }: DiffScannerPanelProps) {
  const [currentLine, setCurrentLine] = useState(0)
  const [scanDone, setScanDone] = useState(false)
  const [visible, setVisible] = useState(false)
  const [breathPhase, setBreathPhase] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const pauseRef = useRef(0)
  const scanRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (active) {
      requestAnimationFrame(() => setVisible(true))
    } else {
      const timer = setTimeout(() => setVisible(false), 200)
      return () => clearTimeout(timer)
    }
  }, [active])

  useEffect(() => {
    if (!active || lines.length === 0) return

    setCurrentLine(0)
    setScanDone(false)
    pauseRef.current = 0

    const baseInterval = 70

    scanRef.current = setInterval(() => {
      setCurrentLine((prev) => {
        if (prev >= lines.length - 1) {
          if (scanRef.current) clearInterval(scanRef.current)
          setScanDone(true)
          return prev
        }
        const kind = classifyLine(lines[prev] ?? '')
        if ((kind === 'add' || kind === 'del') && pauseRef.current < 1) {
          pauseRef.current += 1
          return prev
        }
        pauseRef.current = 0
        return prev + 1
      })
    }, baseInterval)

    return () => {
      if (scanRef.current) clearInterval(scanRef.current)
    }
  }, [active, lines])

  useEffect(() => {
    if (!active || lines.length === 0) return
    const el = containerRef.current
    if (!el) return
    const scrollTarget = currentLine * LINE_HEIGHT
    const currentScroll = el.scrollTop
    const diff = scrollTarget - currentScroll
    const duration = 80
    const startTime = performance.now()

    function animate(now: number) {
      const elapsed = now - startTime
      const t = Math.min(elapsed / duration, 1)
      const ease = t * (2 - t)
      el.scrollTop = currentScroll + diff * ease
      if (t < 1) requestAnimationFrame(animate)
    }

    requestAnimationFrame(animate)
  }, [currentLine, active, lines.length])

  useEffect(() => {
    if (!active) return
    const interval = setInterval(() => {
      setBreathPhase((p) => (p + 1) % 100)
    }, 30)
    return () => clearInterval(interval)
  }, [active])

  if (!visible) return null

  const progress = lines.length > 0 ? Math.round((currentLine / (lines.length - 1)) * 100) : 0
  const breathAlpha = 0.04 + 0.04 * Math.sin((breathPhase / 100) * Math.PI * 2)
  const statusText = scanDone ? '审核完成，正在生成报告...' : `正在审查代码... ${currentLine + 1}/${lines.length} 行`

  return (
    <div
      className="w-full max-w-2xl mt-8 overflow-hidden transition-all duration-200"
      style={{
        opacity: active ? 1 : 0,
        transform: active ? 'translateY(0)' : 'translateY(-6px)',
        borderRadius: 8,
        border: '1px solid #333333',
      }}
    >
      {/* Tab bar */}
      <div
        className="flex items-center gap-2 px-3 select-none"
        style={{ height: 32, background: '#252526', borderBottom: '1px solid #333' }}
      >
        {['#ff5f57', '#febc2e', '#28c840'].map((c) => (
          <span key={c} style={{ width: 10, height: 10, borderRadius: '50%', background: c }} />
        ))}
        <span className="ml-2 text-xs truncate" style={{ color: '#ccc' }}>
          CHANGES &nbsp;—&nbsp; {title}
        </span>
      </div>

      {/* Status bar */}
      <div
        className="flex items-center gap-2 px-3 text-xs select-none"
        style={{ height: 24, background: '#007acc', color: '#fff' }}
      >
        <span className={scanDone ? '' : 'animate-pulse'}>●</span>
        {statusText}
      </div>

      {/* Code area */}
      <div
        ref={containerRef}
        style={{
          height: CODE_HEIGHT,
          overflow: 'hidden',
          background: '#1e1e1e',
          fontFamily: "'JetBrains Mono','Fira Code','Cascadia Code',Consolas,monospace",
          fontSize: 12.5,
          lineHeight: `${LINE_HEIGHT}px`,
        }}
      >
        {lines.map((line, i) => {
          const kind = classifyLine(line)
          const colors = lineColors[kind]
          const isCurrent = i === currentLine

          return (
            <div
              key={i}
              ref={() => {}}
              className="flex transition-none"
              style={{
                background: isCurrent
                  ? `rgba(255,255,255,${breathAlpha})`
                  : colors.bg,
                borderLeft: isCurrent
                  ? `2px solid rgba(255,255,255,${0.3 + 0.3 * Math.sin(breathPhase / 100 * Math.PI * 2)})`
                  : '2px solid transparent',
                transition: 'background 0.1s',
              }}
            >
              <div
                className="shrink-0 text-right select-none"
                style={{
                  width: 44,
                  paddingRight: 8,
                  color: isCurrent ? '#ccc' : '#858585',
                  borderRight: '1px solid #333',
                  marginRight: 12,
                }}
              >
                {i + 1}
              </div>
              <span className="truncate" style={{ color: colors.color }}>
                {line}
              </span>
            </div>
          )
        })}
      </div>

      {/* Progress bar */}
      <div style={{ height: 2, background: '#333' }}>
        <div
          style={{
            height: '100%',
            width: `${scanDone ? 100 : progress}%`,
            background: scanDone ? '#28c840' : '#007acc',
            transition: 'width 0.2s, background 0.3s',
          }}
        />
      </div>
    </div>
  )
}

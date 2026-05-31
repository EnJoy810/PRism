interface Props {
  filename: string
  lines: string[]
}

function parseDiffLines(lines: string[]) {
  type DiffLine = { type: 'add' | 'del' | 'ctx' | 'hunk' | 'meta'; content: string }
  const result: DiffLine[] = []
  for (const line of lines) {
    if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff ') || line.startsWith('index ')) {
      result.push({ type: 'meta', content: line })
    } else if (line.startsWith('@@')) {
      result.push({ type: 'hunk', content: line })
    } else if (line.startsWith('+')) {
      result.push({ type: 'add', content: line.slice(1) })
    } else if (line.startsWith('-')) {
      result.push({ type: 'del', content: line.slice(1) })
    } else {
      result.push({ type: 'ctx', content: line.slice(1) })
    }
  }
  return result
}

const LINE_STYLE: Record<string, React.CSSProperties> = {
  add:  { background: 'rgba(46,160,67,0.15)', color: '#3FB950' },
  del:  { background: 'rgba(248,81,73,0.15)',  color: '#F85149' },
  ctx:  { background: 'transparent',           color: '#E6EDF3' },
  hunk: { background: 'rgba(56,139,253,0.1)',  color: '#79C0FF' },
  meta: { background: 'transparent',           color: '#484F58' },
}

const PREFIX: Record<string, string> = { add: '+', del: '-', ctx: ' ', hunk: '', meta: '' }

export default function FileDiffViewer({ filename, lines }: Props) {
  const parsed = parseDiffLines(lines)
  const visibleLines = parsed.filter(l => l.type !== 'meta')

  return (
    <div
      style={{
        background: '#fff',
        border: '1px solid #E5E7EB',
        borderRadius: 12,
        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
        overflow: 'hidden',
        animation: 'fadeUp 0.18s ease-out',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-3"
        style={{ borderBottom: '1px solid #F1F5F9', background: '#FAFAFA' }}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="#94A3B8" style={{ flexShrink: 0 }}>
          <path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.89 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/>
        </svg>
        <span
          style={{
            fontSize: 11, color: '#334155',
            fontFamily: "'JetBrains Mono', Consolas, monospace",
            flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {filename}
        </span>
      </div>

      {/* Diff body */}
      <div
        style={{
          background: '#0D1117',
          maxHeight: 360,
          overflowY: 'auto',
          fontSize: 12,
          fontFamily: "'JetBrains Mono', Consolas, monospace",
          lineHeight: 1.6,
        }}
      >
        {visibleLines.length === 0 ? (
          <div style={{ padding: '16px', color: '#484F58', textAlign: 'center', fontSize: 12 }}>
            无变更内容
          </div>
        ) : (
          visibleLines.map((line, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                padding: '1px 0',
                ...LINE_STYLE[line.type],
              }}
            >
              {/* 行号列 */}
              <span
                style={{
                  minWidth: 36, padding: '0 10px',
                  color: '#4A5568', userSelect: 'none',
                  borderRight: '1px solid #21262D',
                  textAlign: 'right', flexShrink: 0,
                  fontSize: 11,
                }}
              >
                {line.type === 'hunk' ? '' : i + 1}
              </span>
              {/* 前缀 */}
              <span style={{ padding: '0 6px', flexShrink: 0, opacity: 0.8 }}>
                {PREFIX[line.type]}
              </span>
              {/* 内容 */}
              <span style={{ paddingRight: 16, whiteSpace: 'pre', flex: 1 }}>
                {line.type === 'hunk' ? (
                  <span style={{ color: '#79C0FF' }}>{line.content}</span>
                ) : (
                  line.content
                )}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

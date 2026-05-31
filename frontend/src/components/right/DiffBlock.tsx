export default function DiffBlock({ snippet }: { snippet: string }) {
  return (
    <div
      style={{
        background: '#0D1117',
        borderRadius: 6,
        overflow: 'hidden',
        fontSize: 12,
        fontFamily: "'JetBrains Mono', Consolas, monospace",
        marginBottom: 10,
      }}
    >
      {snippet.split('\n').map((line, i) => {
        const isAdd = line.startsWith('+')
        const isDel = line.startsWith('-')
        return (
          <div
            key={i}
            style={{
              display: 'flex',
              background: isAdd ? 'rgba(46,160,67,0.15)' : isDel ? 'rgba(248,81,73,0.15)' : 'transparent',
              padding: '1px 12px',
            }}
          >
            <span style={{ color: isAdd ? '#3FB950' : isDel ? '#F85149' : '#8B949E', minWidth: 14 }}>
              {isAdd ? '+' : isDel ? '-' : ' '}
            </span>
            <span style={{ color: '#E6EDF3', paddingLeft: 8 }}>{line.slice(isAdd || isDel ? 1 : 0)}</span>
          </div>
        )
      })}
    </div>
  )
}

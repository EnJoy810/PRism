import { type RefObject } from 'react'

interface Props {
  thinkText: string
  streaming: boolean
  thinkDone: boolean
  thinkCollapsed: boolean
  setThinkCollapsed: (v: boolean | ((prev: boolean) => boolean)) => void
  thinkRef: RefObject<HTMLDivElement>
}

export default function ThinkingPanel({
  thinkText,
  streaming,
  thinkDone,
  thinkCollapsed,
  setThinkCollapsed,
  thinkRef,
}: Props) {
  return (
    <div style={{ background: '#fff', border: '1px solid #E5E7EB', borderRadius: 10, overflow: 'hidden', flexShrink: 0 }}>
      <button
        onClick={() => setThinkCollapsed(c => !c)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 16px', background: '#FAFAFA',
          border: 'none', cursor: 'pointer', textAlign: 'left',
          borderBottom: thinkCollapsed ? 'none' : '1px solid #F1F5F9',
        }}
      >
        {streaming && !thinkDone ? (
          <span style={{
            width: 7, height: 7, borderRadius: '50%',
            background: '#8B5CF6', display: 'inline-block',
            animation: 'pulse 1.2s ease-in-out infinite', flexShrink: 0,
          }} />
        ) : (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="#8B5CF6"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
        )}
        <span style={{ fontSize: 12, fontWeight: 700, color: '#6D28D9', flex: 1 }}>
          {streaming && !thinkDone ? 'AI 正在思考…' : '查看思考过程'}
        </span>
        <svg
          width="13" height="13" viewBox="0 0 24 24" fill="#94A3B8"
          style={{ transform: thinkCollapsed ? 'rotate(-90deg)' : 'none', transition: 'transform 0.2s', flexShrink: 0 }}
        >
          <path d="M7 10l5 5 5-5z"/>
        </svg>
      </button>

      {!thinkCollapsed && (
        <div
          ref={thinkRef}
          style={{
            maxHeight: 160, overflowY: 'auto',
            padding: '10px 14px',
            background: '#FAFAFA',
            fontSize: 12, color: '#6B7280',
            fontStyle: 'italic', lineHeight: 1.7,
            whiteSpace: 'pre-wrap',
          }}
        >
          {thinkText}
          {streaming && !thinkDone && (
            <span style={{
              display: 'inline-block', width: 2, height: '1em',
              background: '#8B5CF6', verticalAlign: 'text-bottom',
              animation: 'pulse 0.8s ease-in-out infinite',
            }} />
          )}
        </div>
      )}
    </div>
  )
}

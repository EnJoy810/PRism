import type { PRMeta, ReviewResult } from '../../types/review'

export default function AISummaryCard({ result, meta }: { result: ReviewResult; meta: PRMeta | null }) {
  const readingTime = meta ? Math.max(1, Math.round((meta.files_changed ?? 0) / 2)) : 1
  const priorityFiles = result.priority_files ?? []

  return (
    <div style={{ background: '#fff', border: '1px solid #E5E7EB', borderRadius: 10, overflow: 'hidden', flexShrink: 0 }}>
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid #F1F5F9',
        fontWeight: 700, fontSize: 13, color: '#0F172A',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#2563EB"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm-1 7V3.5L18.5 9H13zM6 20V4h5v7h7v9H6z"/></svg>
        AI 摘要
        <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 400, color: '#94A3B8' }}>
          预计阅读 ~{readingTime} 分钟
        </span>
      </div>
      <div style={{ padding: '12px 16px' }}>
        <p style={{ fontSize: 13, color: '#374151', lineHeight: 1.7, margin: '0 0 12px' }}>
          {result.summary}
        </p>
        {priorityFiles.length > 0 && (
          <>
            <p style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', margin: '0 0 6px' }}>重点关注文件</p>
            <ol style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {priorityFiles.map((f, i) => (
                <li key={i} style={{ fontSize: 12, color: '#374151', fontFamily: "'JetBrains Mono', Consolas, monospace" }}>
                  {f}
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </div>
  )
}

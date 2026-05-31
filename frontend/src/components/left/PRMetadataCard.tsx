import type { PRMeta } from '../../types/review'

interface Props { meta: PRMeta; prUrl: string }

function timeAgo(iso: string): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} minute${mins > 1 ? 's' : ''} ago`
  const h = Math.floor(mins / 60)
  if (h < 24) return `${h} hour${h > 1 ? 's' : ''} ago`
  const d = Math.floor(h / 24)
  return `${d} day${d > 1 ? 's' : ''} ago`
}

function StepBadge({ n }: { n: number }) {
  return (
    <span
      style={{
        width: 22, height: 22, borderRadius: '50%',
        background: '#3b82f6',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 11, fontWeight: 700, color: '#fff', flexShrink: 0,
      }}
    >
      {n}
    </span>
  )
}

export default function PRMetadataCard({ meta, prUrl }: Props) {
  return (
    <div
      style={{
        background: '#ffffff',
        border: '1px solid #E5E7EB',
        borderRadius: 12,
        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-3.5"
        style={{ borderBottom: '1px solid #f1f5f9' }}
      >
        <div className="flex items-center gap-2.5">
          <StepBadge n={2} />
          <span style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>PR 信息</span>
        </div>
        <span
          style={{
            background: '#ecfdf5', border: '1px solid #a7f3d0',
            color: '#059669', fontSize: 11, fontWeight: 700,
            padding: '2px 9px', borderRadius: 20,
          }}
        >
          就绪
        </span>
      </div>

      <div className="px-5 py-4">
        {/* PR title */}
        {meta.pr_title && (
          <a
            href={prUrl}
            target="_blank"
            rel="noreferrer"
            style={{
              display: 'block',
              color: '#0f172a', fontSize: 14, fontWeight: 600,
              lineHeight: 1.5, textDecoration: 'none', marginBottom: 10,
            }}
            onMouseOver={e => { (e.currentTarget as HTMLAnchorElement).style.color = '#4f46e5' }}
            onMouseOut={e => { (e.currentTarget as HTMLAnchorElement).style.color = '#0f172a' }}
          >
            {meta.pr_title}
          </a>
        )}

        {/* Author + timestamps */}
        <div className="flex items-center gap-2 flex-wrap mb-4">
          <img
            src={meta.author_avatar}
            alt={meta.author_name}
            style={{ width: 20, height: 20, borderRadius: '50%', background: '#e2e8f0' }}
            onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
          <span style={{ fontSize: 12, fontWeight: 600, color: '#334155' }}>{meta.author_name}</span>
          {meta.created_at && (
            <span style={{ fontSize: 12, color: '#94a3b8' }}>
              opened {timeAgo(meta.created_at)}
            </span>
          )}
          {meta.updated_at && (
            <span className="flex items-center gap-1" style={{ fontSize: 12, color: '#94a3b8' }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style={{ opacity: 0.6 }}>
                <path d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm.5 5v5.25l4.5 2.67-.75 1.23L11 13V7h1.5z"/>
              </svg>
              Updated {timeAgo(meta.updated_at)}
            </span>
          )}
        </div>

        {/* Branch pills */}
        <div className="flex items-center gap-2 mb-4">
          <span
            style={{
              fontSize: 11, fontWeight: 500,
              background: '#eff6ff', border: '1px solid #bfdbfe',
              borderRadius: 5, padding: '2px 8px', color: '#2563eb',
              display: 'flex', alignItems: 'center', gap: 4,
            }}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style={{ opacity: 0.7 }}>
              <path d="M6 2a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm0 5a3 3 0 0 0 2.83-2h6.34A3 3 0 1 0 18 3a3 3 0 0 0-2.83 2H8.83A3 3 0 0 0 6 7v10a3 3 0 1 0 2 0V7a2 2 0 0 0-2-2z"/>
            </svg>
            {meta.head_branch}
          </span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#94a3b8">
            <path d="M10 17l5-5-5-5v10z"/>
          </svg>
          <span
            style={{
              fontSize: 11, fontWeight: 500,
              background: '#f8fafc', border: '1px solid #e2e8f0',
              borderRadius: 5, padding: '2px 8px', color: '#64748b',
              display: 'flex', alignItems: 'center', gap: 4,
            }}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style={{ opacity: 0.7 }}>
              <path d="M6 2a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm0 5a3 3 0 0 0 2.83-2h6.34A3 3 0 1 0 18 3a3 3 0 0 0-2.83 2H8.83A3 3 0 0 0 6 7v10a3 3 0 1 0 2 0V7a2 2 0 0 0-2-2z"/>
            </svg>
            {meta.base_branch}
          </span>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-2">
          {[
            { icon: '↔', label: '提交数',   value: String(meta.commits),        color: '#0f172a' },
            { icon: '□', label: '变更文件', value: String(meta.files_changed),  color: '#0f172a' },
            { icon: '+', label: '新增行',   value: `+${meta.additions}`,        color: '#059669' },
            { icon: '−', label: '删除行',   value: `−${meta.deletions}`,        color: '#dc2626' },
          ].map(({ icon, label, value, color }) => (
            <div
              key={label}
              className="rounded-lg p-2.5 text-center"
              style={{ background: '#f8fafc', border: '1px solid #f1f5f9' }}
            >
              <div style={{ fontSize: 10, color: '#94a3b8', marginBottom: 3 }}>
                <span style={{ marginRight: 2 }}>{icon}</span>{label}
              </div>
              <div style={{ fontSize: 15, fontWeight: 700, color }}>{value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'

interface FileItem { filename: string; additions: number; deletions: number }
interface Props {
  files: FileItem[]
  selectedFile: string | null
  onSelectFile: (file: string | null) => void
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

export default function ChangedFilesList({ files, selectedFile, onSelectFile }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [search, setSearch] = useState('')

  const filtered = files.filter(f =>
    search ? f.filename.toLowerCase().includes(search.toLowerCase()) : true
  )
  const visible = expanded ? filtered : filtered.slice(0, 5)
  const hidden = filtered.length - 5

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
          <span style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>
            变更文件
          </span>
          <span
            style={{
              background: '#f1f5f9', borderRadius: 10,
              padding: '1px 8px', fontSize: 11, fontWeight: 600, color: '#64748b',
            }}
          >
            {files.length}
          </span>
        </div>

        {/* Search */}
        <div
          className="flex items-center gap-1.5 rounded-lg px-2.5"
          style={{
            background: '#f8fafc', border: '1px solid #e2e8f0', height: 28,
          }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="#94a3b8">
            <path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
          </svg>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜索文件"
            style={{
              background: 'none', border: 'none', outline: 'none',
              fontSize: 11, color: '#0f172a', width: 96,
            }}
          />
        </div>
      </div>

      <div className="py-1">
        {visible.map((f, i) => {
          const isSelected = selectedFile === f.filename
          return (
          <div
            key={i}
            className="flex items-center gap-2.5 px-5 py-2"
            style={{
              cursor: 'pointer', transition: 'background 0.1s',
              background: isSelected ? '#EFF6FF' : 'transparent',
              borderLeft: isSelected ? '2px solid #2563EB' : '2px solid transparent',
            }}
            onClick={() => onSelectFile(isSelected ? null : f.filename)}
            onMouseEnter={e => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = '#f8fafc' }}
            onMouseLeave={e => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
          >
            {/* File icon */}
            <svg width="13" height="13" viewBox="0 0 24 24" fill="#94a3b8" style={{ flexShrink: 0 }}>
              <path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.89 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/>
            </svg>
            <span
              style={{
                fontSize: 12, color: '#334155',
                fontFamily: "'JetBrains Mono','Fira Code',Consolas,monospace",
                flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}
            >
              {f.filename}
            </span>
            <div className="flex items-center gap-2 shrink-0">
              <span style={{ fontSize: 11, fontWeight: 700, color: '#059669' }}>+{f.additions}</span>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#dc2626' }}>-{f.deletions}</span>
            </div>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="#cbd5e1" style={{ flexShrink: 0 }}>
              <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>
            </svg>
          </div>
          )
        })}

        {!expanded && hidden > 0 && (
          <button
            onClick={() => setExpanded(true)}
            className="flex items-center gap-1.5"
            style={{
              width: '100%', padding: '8px 20px', background: 'none',
              border: 'none', cursor: 'pointer', color: '#64748b',
              fontSize: 12, fontWeight: 500,
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
            </svg>
            还有 {hidden} 个文件
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M7 10l5 5 5-5z"/>
            </svg>
          </button>
        )}

        {expanded && (
          <button
            onClick={() => setExpanded(false)}
            style={{
              width: '100%', padding: '8px 20px', background: 'none',
              border: 'none', cursor: 'pointer', color: '#64748b', fontSize: 12,
            }}
          >
            收起 ▲
          </button>
        )}
      </div>
    </div>
  )
}

import { useState } from 'react'
import { Typography } from 'antd'

const { Text } = Typography

interface FileItem { filename: string; additions: number; deletions: number }
interface Props { files: FileItem[] }

export default function ChangedFilesList({ files }: Props) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? files : files.slice(0, 8)
  const hidden = files.length - 8

  return (
    <div className="rounded-xl overflow-hidden" style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)' }}>
      <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--hairline)' }}>
        <Text style={{ color: 'var(--ink)', fontSize: 13, fontWeight: 600 }}>
          变更文件
          <span style={{ marginLeft: 6, background: 'var(--surface-el)', borderRadius: 10, padding: '1px 7px', fontSize: 11, color: 'var(--ink-ash)' }}>
            {files.length}
          </span>
        </Text>
      </div>
      <div className="py-1">
        {visible.map((f, i) => (
          <div key={i} className="flex items-center justify-between px-4 py-1.5 hover:opacity-80">
            <Text style={{ fontSize: 12, color: 'var(--ink-body)', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>
              {f.filename}
            </Text>
            <div className="flex gap-2 shrink-0">
              <Text style={{ fontSize: 11, color: 'var(--accent-green)' }}>+{f.additions}</Text>
              <Text style={{ fontSize: 11, color: 'var(--accent-red)' }}>-{f.deletions}</Text>
            </div>
          </div>
        ))}
        {!expanded && hidden > 0 && (
          <button
            onClick={() => setExpanded(true)}
            style={{ width: '100%', padding: '6px 16px', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-ash)', fontSize: 12, textAlign: 'left' }}
          >
            + {hidden} 个文件
          </button>
        )}
      </div>
    </div>
  )
}

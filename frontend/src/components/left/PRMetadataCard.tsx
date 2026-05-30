import { Typography } from 'antd'
import type { PRMeta } from '../../types/review'

const { Text } = Typography

interface Props {
  meta: PRMeta
  prUrl: string
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}

export default function PRMetadataCard({ meta, prUrl }: Props) {
  return (
    <div className="rounded-xl p-4" style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)' }}>
      {/* PR 链接 */}
      <a
        href={prUrl}
        target="_blank"
        rel="noreferrer"
        style={{ color: 'var(--ink)', fontSize: 14, fontWeight: 600, lineHeight: 1.5, display: 'block', marginBottom: 10, textDecoration: 'none' }}
        onMouseOver={e => { e.currentTarget.style.textDecoration = 'underline' }}
        onMouseOut={e => { e.currentTarget.style.textDecoration = 'none' }}
      >
        Pull Request
      </a>

      {/* 作者 */}
      <div className="flex items-center gap-2 mb-3">
        <img
          src={meta.author_avatar}
          alt={meta.author_name}
          style={{ width: 20, height: 20, borderRadius: '50%', background: 'var(--surface-el)' }}
          onError={e => { e.currentTarget.style.display = 'none' }}
        />
        <Text style={{ color: 'var(--ink-mute)', fontSize: 12 }}>
          {meta.author_name}
          {meta.updated_at && <>&nbsp;·&nbsp;更新于 {timeAgo(meta.updated_at)}</>}
        </Text>
      </div>

      {/* 分支 */}
      <div className="flex items-center gap-2 mb-4">
        <code style={{ fontSize: 11, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 4, padding: '2px 6px', color: 'var(--accent-blue)' }}>
          {meta.head_branch}
        </code>
        <span style={{ color: 'var(--ink-stone)', fontSize: 12 }}>→</span>
        <code style={{ fontSize: 11, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 4, padding: '2px 6px', color: 'var(--ink-mute)' }}>
          {meta.base_branch}
        </code>
      </div>

      {/* 统计数字 */}
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: '提交', value: meta.commits },
          { label: '文件', value: meta.files_changed },
          { label: '新增', value: `+${meta.additions}`, color: 'var(--accent-green)' },
          { label: '删除', value: `-${meta.deletions}`, color: 'var(--accent-red)' },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded-lg p-2 text-center" style={{ background: 'var(--surface)' }}>
            <Text style={{ fontSize: 11, color: 'var(--ink-ash)', display: 'block' }}>{label}</Text>
            <Text style={{ fontSize: 15, fontWeight: 600, color: color ?? 'var(--ink)' }}>{value}</Text>
          </div>
        ))}
      </div>
    </div>
  )
}

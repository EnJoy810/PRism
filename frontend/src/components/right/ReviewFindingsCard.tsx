import { useState } from 'react'
import type { ReviewIssue, Severity } from '../../types/review'
import DiffBlock from './DiffBlock'

type FilterTab = 'all' | Severity

const SEV_LABEL: Record<Severity, string> = { ERROR: 'Critical', WARNING: 'Warning', INFO: 'Suggestion' }
const SEV_COLOR: Record<Severity, { bg: string; text: string }> = {
  ERROR:   { bg: '#EF4444', text: '#fff' },
  WARNING: { bg: '#F59E0B', text: '#fff' },
  INFO:    { bg: '#3B82F6', text: '#fff' },
}

function IssueRow({
  issue, expanded, onToggle,
}: {
  issue: ReviewIssue
  expanded: boolean
  onToggle: () => void
}) {
  const sev = SEV_COLOR[issue.severity]
  return (
    <div style={{ borderBottom: '1px solid #F1F5F9' }}>
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 16px', background: expanded ? '#F8FAFF' : 'transparent',
          cursor: 'pointer', transition: 'background 0.1s',
        }}
        onClick={onToggle}
      >
        <span style={{ background: sev.bg, color: sev.text, fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4, letterSpacing: '0.04em', flexShrink: 0 }}>
          {SEV_LABEL[issue.severity]}
        </span>
        <span style={{ fontSize: 11, color: '#64748B', fontFamily: "'JetBrains Mono', Consolas, monospace", flexShrink: 0, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {issue.file}{issue.line ? ` · ${issue.line}L` : ''}
        </span>
        <span style={{ fontSize: 13, color: '#0F172A', fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {issue.title}
        </span>
        <button
          onClick={e => { e.stopPropagation(); navigator.clipboard.writeText(`${issue.file}: ${issue.title}`) }}
          style={{ background: 'none', border: '1px solid #E5E7EB', borderRadius: 5, cursor: 'pointer', padding: '3px 8px', fontSize: 11, color: '#64748B', flexShrink: 0 }}
        >
          复制
        </button>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#94A3B8"
          style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s', flexShrink: 0 }}>
          <path d="M7 10l5 5 5-5z"/>
        </svg>
      </div>
      {expanded && (
        <div style={{ padding: '0 16px 16px', background: '#F8FAFF' }}>
          {issue.diff_snippet && <DiffBlock snippet={issue.diff_snippet} />}
          <p style={{ fontSize: 13, color: '#374151', marginBottom: 8, lineHeight: 1.6 }}>{issue.description}</p>
          {issue.suggestion && (
            <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 6, padding: '8px 12px', fontSize: 12, color: '#166534', marginBottom: 12 }}>
              <strong>建议：</strong>{issue.suggestion}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface Props {
  issues: ReviewIssue[]
  filterTab: FilterTab
  setFilterTab: (t: FilterTab) => void
  expandedId: string | null
  setExpandedId: (id: string | null) => void
}

export default function ReviewFindingsCard({ issues, filterTab, setFilterTab, expandedId, setExpandedId }: Props) {
  const [groupOpen, setGroupOpen] = useState<Record<Severity, boolean>>({ ERROR: true, WARNING: false, INFO: false })

  const counts = {
    all: issues.length,
    ERROR: issues.filter(i => i.severity === 'ERROR').length,
    WARNING: issues.filter(i => i.severity === 'WARNING').length,
    INFO: issues.filter(i => i.severity === 'INFO').length,
  }

  const filtered = filterTab === 'all' ? issues : issues.filter(i => i.severity === filterTab)
  const byGroup: Record<Severity, ReviewIssue[]> = { ERROR: [], WARNING: [], INFO: [] }
  for (const issue of filtered) byGroup[issue.severity].push(issue)

  const tabConfig: [FilterTab, string][] = [
    ['all', `全部 ${counts.all}`],
    ['ERROR', `严重 ${counts.ERROR}`],
    ['WARNING', `警告 ${counts.WARNING}`],
    ['INFO', `提示 ${counts.INFO}`],
  ]

  const groupMeta: { sev: Severity; label: string }[] = [
    { sev: 'ERROR', label: 'Critical' },
    { sev: 'WARNING', label: 'Warning' },
    { sev: 'INFO', label: 'Suggestion' },
  ]

  return (
    <div style={{ background: '#fff', border: '1px solid #E5E7EB', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid #F1F5F9',
        fontWeight: 700, fontSize: 13, color: '#0F172A',
        display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#EF4444"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
        审查发现
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {tabConfig.map(([tab, label]) => (
            <button
              key={tab}
              onClick={() => setFilterTab(tab)}
              style={{
                padding: '3px 10px', borderRadius: 20,
                border: filterTab === tab ? '1px solid #BFDBFE' : '1px solid #E5E7EB',
                background: filterTab === tab ? '#EFF6FF' : 'transparent',
                color: filterTab === tab ? '#2563EB' : '#64748B',
                fontSize: 11, fontWeight: filterTab === tab ? 700 : 400,
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div>
        {groupMeta.map(({ sev, label }) => {
          const items = byGroup[sev]
          if (items.length === 0) return null
          const isOpen = groupOpen[sev]
          const cfg = SEV_COLOR[sev]
          return (
            <div key={sev} style={{ borderBottom: '1px solid #F1F5F9' }}>
              <button
                onClick={() => setGroupOpen(g => ({ ...g, [sev]: !g[sev] }))}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                  padding: '8px 16px', background: '#FAFAFA',
                  border: 'none', cursor: 'pointer', textAlign: 'left',
                }}
              >
                <span style={{ background: cfg.bg, color: cfg.text, fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 4 }}>
                  {label}
                </span>
                <span style={{ fontSize: 12, color: '#374151' }}>({items.length})</span>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="#94A3B8"
                  style={{ marginLeft: 'auto', transform: isOpen ? 'none' : 'rotate(-90deg)', transition: 'transform 0.15s' }}>
                  <path d="M7 10l5 5 5-5z"/>
                </svg>
              </button>
              {isOpen && items.map((issue, i) => {
                const id = `${issue.file}:${issue.line}:${sev}:${i}`
                return (
                  <IssueRow
                    key={id}
                    issue={issue}
                    expanded={expandedId === id}
                    onToggle={() => setExpandedId(expandedId === id ? null : id)}
                  />
                )
              })}
            </div>
          )
        })}
        {filtered.length === 0 && (
          <div style={{ padding: '20px 16px', textAlign: 'center', color: '#94A3B8', fontSize: 13 }}>
            该分类下暂无问题
          </div>
        )}
      </div>
    </div>
  )
}

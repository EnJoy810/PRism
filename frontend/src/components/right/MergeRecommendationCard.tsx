import type { MergeRecommendation } from '../../types/review'

const DECISION_CONFIG: Record<string, { bg: string; text: string; border: string; label: string }> = {
  APPROVE:         { bg: '#ECFDF5', text: '#059669', border: '#A7F3D0', label: 'APPROVE' },
  REQUEST_CHANGES: { bg: '#FEF2F2', text: '#DC2626', border: '#FECACA', label: 'REQUEST CHANGES' },
  COMMENT:         { bg: '#FFFBEB', text: '#D97706', border: '#FDE68A', label: 'COMMENT' },
}

export default function MergeRecommendationCard({ rec }: { rec: MergeRecommendation }) {
  const cfg = DECISION_CONFIG[rec.decision] ?? DECISION_CONFIG.COMMENT

  return (
    <div style={{ background: '#fff', border: '1px solid #E5E7EB', borderRadius: 10, overflow: 'hidden', flexShrink: 0 }}>
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid #F1F5F9',
        fontWeight: 700, fontSize: 13, color: '#0F172A',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#059669"><path d="M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z"/></svg>
        合并建议
      </div>
      <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ background: cfg.bg, color: cfg.text, border: `1px solid ${cfg.border}`, fontSize: 12, fontWeight: 700, padding: '5px 14px', borderRadius: 6, letterSpacing: '0.04em' }}>
            {cfg.label}
          </span>
          <span style={{ fontSize: 13, color: '#374151' }}>置信度</span>
          <div style={{ flex: 1, background: '#F1F5F9', borderRadius: 99, height: 8, overflow: 'hidden' }}>
            <div style={{
              height: '100%', width: `${rec.confidence}%`,
              background: rec.decision === 'APPROVE' ? '#059669' : rec.decision === 'REQUEST_CHANGES' ? '#EF4444' : '#F59E0B',
              borderRadius: 99, transition: 'width 0.6s ease',
            }} />
          </div>
          <span style={{ fontSize: 12, fontWeight: 700, color: '#374151', flexShrink: 0 }}>{rec.confidence}%</span>
        </div>
        {rec.reasons.length > 0 && (
          <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 5 }}>
            {rec.reasons.map((r, i) => (
              <li key={i} style={{ fontSize: 13, color: '#374151', lineHeight: 1.5 }}>{r}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

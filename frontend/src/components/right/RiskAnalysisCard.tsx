import type { RiskArea } from '../../types/review'

const RISK_CONFIG: Record<string, { bg: string; text: string; border: string; label: string }> = {
  HIGH:   { bg: '#FEF2F2', text: '#DC2626', border: '#FECACA', label: '高风险' },
  MEDIUM: { bg: '#FFFBEB', text: '#D97706', border: '#FDE68A', label: '中等风险' },
  LOW:    { bg: '#ECFDF5', text: '#059669', border: '#A7F3D0', label: '低风险' },
}

export default function RiskAnalysisCard({ riskAreas }: { riskAreas: RiskArea[] }) {
  const grouped: Record<string, RiskArea[]> = { HIGH: [], MEDIUM: [], LOW: [] }
  for (const r of riskAreas) grouped[r.level]?.push(r)

  return (
    <div style={{ background: '#fff', border: '1px solid #E5E7EB', borderRadius: 10, overflow: 'hidden', flexShrink: 0 }}>
      <div style={{
        padding: '10px 16px', borderBottom: '1px solid #F1F5F9',
        fontWeight: 700, fontSize: 13, color: '#0F172A',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#F59E0B"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v6z"/></svg>
        风险分析
      </div>
      <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {(['HIGH', 'MEDIUM', 'LOW'] as const).map(level => {
          const items = grouped[level]
          if (!items || items.length === 0) return null
          const cfg = RISK_CONFIG[level]
          return (
            <div key={level}>
              <div style={{ fontSize: 11, fontWeight: 700, color: cfg.text, marginBottom: 6, letterSpacing: '0.05em' }}>
                {cfg.label} ({items.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {items.map((r, i) => (
                  <div key={i} style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 6, padding: '8px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                      <span style={{
                        fontSize: 10, fontWeight: 700, fontFamily: "'JetBrains Mono', Consolas, monospace",
                        color: cfg.text, flexShrink: 0, maxWidth: 200,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {r.file}
                      </span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: '#0F172A' }}>{r.title}</span>
                    </div>
                    <p style={{ fontSize: 12, color: '#374151', margin: 0, lineHeight: 1.5 }}>{r.impact}</p>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
        {riskAreas.length === 0 && (
          <p style={{ fontSize: 13, color: '#94A3B8', textAlign: 'center', margin: '8px 0' }}>无风险项</p>
        )}
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useSettings } from '../../stores/reviewOptions'

const NAV_ITEMS = [
  { label: 'Dashboard', active: false },
  { label: 'Pull Requests', active: false },
  { label: 'AI Review', active: true },
  { label: 'Repositories', active: false },
]

const PRESET_MODELS = [
  { label: 'DeepSeek V4 Flash', desc: '响应快，适合日常 Review', value: 'deepseek-v4-flash' },
  { label: 'DeepSeek V4 Pro', desc: '推理深，适合复杂变更', value: 'deepseek-v4-pro' },
]

function SettingsDrawer({ onClose }: { onClose: () => void }) {
  const { model, setModel } = useSettings()
  const [custom, setCustom] = useState(
    PRESET_MODELS.find(m => m.value === model) ? '' : model
  )
  const isPreset = PRESET_MODELS.some(m => m.value === model)

  function applyCustom(val: string) {
    setCustom(val)
    if (val.trim()) setModel(val.trim())
  }

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 200,
          background: 'rgba(0,0,0,0.25)',
        }}
      />
      {/* Drawer */}
      <div
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0,
          width: 340, zIndex: 201,
          background: '#fff',
          borderLeft: '1px solid #E5E7EB',
          boxShadow: '-4px 0 24px rgba(0,0,0,0.10)',
          display: 'flex', flexDirection: 'column',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '18px 20px 16px',
          borderBottom: '1px solid #F1F5F9',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: '#0F172A' }}>设置</span>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#94A3B8', borderRadius: 6 }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: '#94A3B8', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 12 }}>
            模型
          </p>

          {/* Preset options */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
            {PRESET_MODELS.map(m => (
              <button
                key={m.value}
                onClick={() => { setModel(m.value); setCustom('') }}
                style={{
                  textAlign: 'left', padding: '10px 14px', borderRadius: 8, cursor: 'pointer',
                  border: model === m.value && isPreset ? '1.5px solid #2563EB' : '1px solid #E5E7EB',
                  background: model === m.value && isPreset ? '#EFF6FF' : '#F8FAFC',
                  transition: 'all 0.1s',
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 600, color: model === m.value && isPreset ? '#2563EB' : '#0F172A', marginBottom: 2 }}>
                  {m.label}
                </div>
                <div style={{ fontSize: 11, color: '#94A3B8' }}>{m.desc}</div>
              </button>
            ))}
          </div>

          {/* Custom model input */}
          <div>
            <p style={{ fontSize: 12, color: '#64748B', marginBottom: 6 }}>自定义模型 ID</p>
            <input
              value={custom}
              onChange={e => applyCustom(e.target.value)}
              placeholder="如 gpt-4o、claude-opus-4-8"
              style={{
                width: '100%', height: 36, padding: '0 12px', borderRadius: 7,
                border: !isPreset && model ? '1.5px solid #2563EB' : '1px solid #E5E7EB',
                background: '#F8FAFC', fontSize: 12, color: '#0F172A',
                fontFamily: "'JetBrains Mono', Consolas, monospace",
                outline: 'none', boxSizing: 'border-box',
              }}
            />
            <p style={{ fontSize: 11, color: '#94A3B8', marginTop: 5 }}>
              支持任意 OpenAI 兼容接口的模型 ID
            </p>
          </div>

          {/* Current model indicator */}
          <div style={{ marginTop: 20, padding: '10px 14px', background: '#F8FAFC', borderRadius: 8, border: '1px solid #F1F5F9' }}>
            <p style={{ fontSize: 11, color: '#94A3B8', marginBottom: 3 }}>当前使用</p>
            <p style={{ fontSize: 12, fontWeight: 600, color: '#0F172A', fontFamily: "'JetBrains Mono', monospace" }}>
              {model}
            </p>
          </div>
        </div>
      </div>
    </>
  )
}

export default function Navbar() {
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <>
      <header
        style={{
          height: 54,
          background: '#ffffff',
          borderBottom: '1px solid var(--hairline)',
          boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 28px',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 mr-10">
          <div
            style={{
              width: 30, height: 30, borderRadius: 8,
              background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 800, color: '#fff',
              fontFamily: 'monospace', letterSpacing: '-0.5px',
            }}
          >
            {'</>'}
          </div>
          <span style={{ color: '#0f172a', fontWeight: 700, fontSize: 15 }}>ReviewAI</span>
          <span style={{
            background: '#f1f5f9', border: '1px solid #e2e8f0',
            color: '#64748b', fontSize: 10, fontWeight: 600,
            padding: '1px 7px', borderRadius: 4, letterSpacing: '0.04em',
          }}>
            Beta
          </span>
        </div>

        {/* Nav */}
        <nav className="flex items-center gap-0.5 flex-1">
          {NAV_ITEMS.map(({ label, active }) => (
            <button
              key={label}
              style={{
                padding: '6px 14px', borderRadius: 6, fontSize: 13,
                fontWeight: active ? 600 : 400, border: 'none',
                background: 'transparent',
                color: active ? '#4f46e5' : '#475569',
                cursor: 'pointer', position: 'relative',
              }}
            >
              {label}
              {active && (
                <span style={{
                  position: 'absolute', bottom: -13, left: '50%',
                  transform: 'translateX(-50%)', width: '55%', height: 2,
                  background: '#4f46e5', borderRadius: '1px 1px 0 0',
                }} />
              )}
            </button>
          ))}
        </nav>

        {/* Right */}
        <div className="flex items-center gap-3">
          {/* Settings gear */}
          <button
            onClick={() => setSettingsOpen(true)}
            title="设置"
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              padding: 6, color: '#94A3B8', borderRadius: 7,
              transition: 'color 0.15s',
            }}
            onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.color = '#475569'}
            onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.color = '#94A3B8'}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
            </svg>
          </button>

          {/* Notification bell */}
          <button style={{ position: 'relative', background: 'none', border: 'none', cursor: 'pointer', padding: 6, color: '#64748b', borderRadius: 7 }}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/>
            </svg>
            <span style={{
              position: 'absolute', top: 3, right: 3,
              width: 15, height: 15, background: '#ef4444', borderRadius: '50%',
              fontSize: 9, fontWeight: 700, color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: '1.5px solid #fff',
            }}>3</span>
          </button>

          {/* User */}
          <div className="flex items-center gap-2" style={{ cursor: 'pointer', padding: '4px 8px', borderRadius: 8, border: '1px solid var(--hairline)', background: '#f8fafc' }}>
            <img
              src="https://api.dicebear.com/7.x/avataaars/svg?seed=alex"
              alt=""
              style={{ width: 26, height: 26, borderRadius: '50%', background: '#e2e8f0' }}
              onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
            />
            <div style={{ lineHeight: 1.25 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#0f172a' }}>Alex Chen</div>
              <div style={{ fontSize: 10, color: '#94a3b8' }}>acme-dev</div>
            </div>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="#94a3b8"><path d="M7 10l5 5 5-5z"/></svg>
          </div>
        </div>
      </header>

      {settingsOpen && <SettingsDrawer onClose={() => setSettingsOpen(false)} />}
    </>
  )
}

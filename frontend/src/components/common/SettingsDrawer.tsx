import { useState } from 'react'
import { useSettings } from '../../stores/reviewOptions'

const PRESETS = [
  {
    label: 'DeepSeek V4 Flash',
    desc: '响应快，适合日常 Review',
    model: 'deepseek-v4-flash',
    baseUrl: 'https://api.deepseek.com/v1',
  },
  {
    label: 'DeepSeek V4 Pro',
    desc: '推理深，适合复杂变更',
    model: 'deepseek-v4-pro',
    baseUrl: 'https://api.deepseek.com/v1',
  },
]

const fieldStyle: React.CSSProperties = {
  width: '100%', height: 36, padding: '0 12px', borderRadius: 7,
  border: '1px solid #E5E7EB', background: '#F8FAFC',
  fontSize: 12, color: '#0F172A', outline: 'none',
  fontFamily: "'JetBrains Mono', Consolas, monospace",
  boxSizing: 'border-box',
}

const labelStyle: React.CSSProperties = {
  fontSize: 11, color: '#64748B', marginBottom: 5, display: 'block',
}

const sectionTitle: React.CSSProperties = {
  fontSize: 11, fontWeight: 600, color: '#94A3B8',
  letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 10,
}

function Drawer({ onClose }: { onClose: () => void }) {
  const { model, baseUrl, apiKey, setModel, setBaseUrl, setApiKey } = useSettings()
  const [keyVisible, setKeyVisible] = useState(false)

  const activePreset = PRESETS.find(p => p.model === model && p.baseUrl === baseUrl)

  function applyPreset(p: typeof PRESETS[number]) {
    setModel(p.model)
    setBaseUrl(p.baseUrl)
  }

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,0.2)' }} />
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 340, zIndex: 201,
        background: '#fff', borderLeft: '1px solid #E5E7EB',
        boxShadow: '-4px 0 24px rgba(0,0,0,0.10)',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #F1F5F9', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>设置</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: '#94A3B8', borderRadius: 6 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 24 }}>

          {/* Presets */}
          <div>
            <p style={sectionTitle}>快速选择</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {PRESETS.map(p => {
                const active = activePreset?.model === p.model
                return (
                  <button key={p.model} onClick={() => applyPreset(p)} style={{
                    textAlign: 'left', padding: '10px 14px', borderRadius: 8, cursor: 'pointer',
                    border: active ? '1.5px solid #2563EB' : '1px solid #E5E7EB',
                    background: active ? '#EFF6FF' : '#F8FAFC',
                    transition: 'all 0.1s',
                  }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: active ? '#2563EB' : '#0F172A', marginBottom: 2 }}>{p.label}</div>
                    <div style={{ fontSize: 11, color: '#94A3B8' }}>{p.desc}</div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Custom config */}
          <div>
            <p style={sectionTitle}>自定义配置</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label style={labelStyle}>Model ID</label>
                <input
                  value={model}
                  onChange={e => setModel(e.target.value)}
                  placeholder="如 gpt-4o、claude-opus-4-8"
                  style={fieldStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>Base URL</label>
                <input
                  value={baseUrl}
                  onChange={e => setBaseUrl(e.target.value)}
                  placeholder="https://api.openai.com/v1"
                  style={fieldStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>API Key</label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={keyVisible ? 'text' : 'password'}
                    value={apiKey}
                    onChange={e => setApiKey(e.target.value)}
                    placeholder="sk-..."
                    style={{ ...fieldStyle, paddingRight: 36 }}
                  />
                  <button
                    onClick={() => setKeyVisible(v => !v)}
                    style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#94A3B8', padding: 0 }}
                  >
                    {keyVisible
                      ? <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/></svg>
                      : <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
                    }
                  </button>
                </div>
                <p style={{ fontSize: 11, color: '#94A3B8', marginTop: 4 }}>仅存储在本地，不会上传服务器</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

// 受控模式：传入 onClose 时直接渲染 Drawer（由父级控制 open 状态）
// 非受控模式：不传 onClose 时内置触发按钮
export default function SettingsDrawer({ onClose }: { onClose?: () => void } = {}) {
  const [open, setOpen] = useState(false)

  if (onClose) {
    return <Drawer onClose={onClose} />
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="设置"
        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 5, color: '#94A3B8', borderRadius: 6, display: 'flex', alignItems: 'center' }}
        onMouseEnter={e => (e.currentTarget as HTMLButtonElement).style.color = '#475569'}
        onMouseLeave={e => (e.currentTarget as HTMLButtonElement).style.color = '#94A3B8'}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
        </svg>
      </button>
      {open && <Drawer onClose={() => setOpen(false)} />}
    </>
  )
}

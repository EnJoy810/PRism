const NAV_ITEMS = [
  { label: 'Dashboard', active: false },
  { label: 'Pull Requests', active: false },
  { label: 'AI Review', active: true },
  { label: 'Repositories', active: false },
  { label: 'Settings', active: false },
]

export default function Navbar() {
  return (
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
            width: 30,
            height: 30,
            borderRadius: 8,
            background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 11,
            fontWeight: 800,
            color: '#fff',
            fontFamily: 'monospace',
            letterSpacing: '-0.5px',
          }}
        >
          {'</>'}
        </div>
        <span style={{ color: '#0f172a', fontWeight: 700, fontSize: 15 }}>ReviewAI</span>
        <span
          style={{
            background: '#f1f5f9',
            border: '1px solid #e2e8f0',
            color: '#64748b',
            fontSize: 10,
            fontWeight: 600,
            padding: '1px 7px',
            borderRadius: 4,
            letterSpacing: '0.04em',
          }}
        >
          Beta
        </span>
      </div>

      {/* Nav */}
      <nav className="flex items-center gap-0.5 flex-1">
        {NAV_ITEMS.map(({ label, active }) => (
          <button
            key={label}
            style={{
              padding: '6px 14px',
              borderRadius: 6,
              fontSize: 13,
              fontWeight: active ? 600 : 400,
              border: 'none',
              background: 'transparent',
              color: active ? '#4f46e5' : '#475569',
              cursor: 'pointer',
              position: 'relative',
            }}
          >
            {label}
            {active && (
              <span
                style={{
                  position: 'absolute',
                  bottom: -13,
                  left: '50%',
                  transform: 'translateX(-50%)',
                  width: '55%',
                  height: 2,
                  background: '#4f46e5',
                  borderRadius: '1px 1px 0 0',
                }}
              />
            )}
          </button>
        ))}
      </nav>

      {/* Right */}
      <div className="flex items-center gap-3">
        <button
          style={{
            position: 'relative',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '6px',
            color: '#64748b',
            borderRadius: 7,
          }}
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/>
          </svg>
          <span
            style={{
              position: 'absolute',
              top: 3,
              right: 3,
              width: 15,
              height: 15,
              background: '#ef4444',
              borderRadius: '50%',
              fontSize: 9,
              fontWeight: 700,
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1.5px solid #fff',
            }}
          >
            3
          </span>
        </button>

        <div
          className="flex items-center gap-2"
          style={{
            cursor: 'pointer',
            padding: '4px 8px',
            borderRadius: 8,
            border: '1px solid var(--hairline)',
            background: '#f8fafc',
          }}
        >
          <img
            src="https://api.dicebear.com/7.x/avataaars/svg?seed=alex"
            alt="Alex Chen"
            style={{ width: 26, height: 26, borderRadius: '50%', background: '#e2e8f0' }}
            onError={e => {
              const el = e.currentTarget as HTMLImageElement
              el.style.display = 'none'
            }}
          />
          <div style={{ lineHeight: 1.25 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#0f172a' }}>Alex Chen</div>
            <div style={{ fontSize: 10, color: '#94a3b8' }}>acme-dev</div>
          </div>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="#94a3b8">
            <path d="M7 10l5 5 5-5z"/>
          </svg>
        </div>
      </div>
    </header>
  )
}

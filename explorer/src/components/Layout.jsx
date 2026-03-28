import React, { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

const navLinks = [
  { to: '/papers', label: 'Papers' },
  { to: '/connections', label: 'Connections' },
  { to: '/bridge', label: 'Bridge Query' },
]

export default function Layout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)

  function handleSearch(e) {
    e.preventDefault()
    if (q.trim()) {
      navigate(`/search?q=${encodeURIComponent(q.trim())}`)
      setQ('')
      setMenuOpen(false)
    }
  }

  return (
    <div className="min-h-screen" style={{ background: '#0a0a0f', color: '#e0e0e8' }}>
      {/* Header */}
      <header style={{ background: '#0d0d18', borderBottom: '1px solid #1e1e2e' }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-14 gap-4">
            {/* Logo */}
            <Link to="/" className="flex-shrink-0 flex items-center gap-2">
              <span style={{ fontSize: 22, color: '#7c6af7' }}>⬡</span>
              <span style={{ fontWeight: 700, fontSize: 16, color: '#e0e0e8', letterSpacing: '-0.3px' }}>
                Decoded
              </span>
              <span className="hidden sm:block" style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                Literature Connectome
              </span>
            </Link>

            {/* Desktop nav */}
            <nav className="hidden md:flex items-center gap-1">
              {navLinks.map(({ to, label }) => {
                const active = location.pathname === to
                return (
                  <Link
                    key={to}
                    to={to}
                    style={{
                      padding: '6px 12px',
                      borderRadius: 6,
                      fontSize: 13,
                      fontWeight: active ? 600 : 400,
                      color: active ? '#7c6af7' : '#9ca3af',
                      background: active ? 'rgba(124,106,247,0.1)' : 'transparent',
                      transition: 'all 0.15s',
                    }}
                  >
                    {label}
                  </Link>
                )
              })}
            </nav>

            {/* Search */}
            <form onSubmit={handleSearch} className="hidden sm:flex items-center gap-2 flex-1 max-w-xs">
              <input
                value={q}
                onChange={e => setQ(e.target.value)}
                placeholder="Search papers..."
                style={{
                  flex: 1,
                  background: '#12121e',
                  border: '1px solid #1e1e2e',
                  borderRadius: 6,
                  padding: '6px 12px',
                  fontSize: 13,
                  color: '#e0e0e8',
                  outline: 'none',
                  minWidth: 0,
                }}
              />
              <button
                type="submit"
                style={{
                  background: '#7c6af7',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 6,
                  padding: '6px 14px',
                  fontSize: 13,
                  cursor: 'pointer',
                  flexShrink: 0,
                }}
              >
                Search
              </button>
            </form>

            {/* Mobile menu toggle */}
            <button
              className="md:hidden"
              onClick={() => setMenuOpen(!menuOpen)}
              style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', padding: 4 }}
              aria-label="Toggle menu"
            >
              {menuOpen ? (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              ) : (
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Mobile menu */}
        {menuOpen && (
          <div style={{ borderTop: '1px solid #1e1e2e', background: '#0d0d18', padding: '12px 16px' }}>
            <form onSubmit={handleSearch} className="flex gap-2 mb-3">
              <input
                value={q}
                onChange={e => setQ(e.target.value)}
                placeholder="Search papers..."
                style={{
                  flex: 1,
                  background: '#12121e',
                  border: '1px solid #1e1e2e',
                  borderRadius: 6,
                  padding: '8px 12px',
                  fontSize: 14,
                  color: '#e0e0e8',
                  outline: 'none',
                }}
              />
              <button
                type="submit"
                style={{
                  background: '#7c6af7',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 6,
                  padding: '8px 14px',
                  fontSize: 14,
                  cursor: 'pointer',
                }}
              >
                Go
              </button>
            </form>
            {navLinks.map(({ to, label }) => (
              <Link
                key={to}
                to={to}
                onClick={() => setMenuOpen(false)}
                style={{
                  display: 'block',
                  padding: '10px 12px',
                  borderRadius: 6,
                  fontSize: 14,
                  color: location.pathname === to ? '#7c6af7' : '#e0e0e8',
                  background: location.pathname === to ? 'rgba(124,106,247,0.1)' : 'transparent',
                }}
              >
                {label}
              </Link>
            ))}
          </div>
        )}
      </header>

      {/* Page content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {children}
      </main>
    </div>
  )
}

import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Link, NavLink, useNavigate } from 'react-router-dom'
import { API, s } from './shared.js'
import { AuthProvider, useAuth } from './auth.jsx'
import { navLinkStyle } from './components/ui.jsx'

import PapersPage from './pages/PapersPage.jsx'
import PaperDetailPage from './pages/PaperDetailPage.jsx'
import ConnectionsPage from './pages/ConnectionsPage.jsx'
import ConvergencesPage from './pages/ConvergencesPage.jsx'
import GapsPage from './pages/GapsPage.jsx'
import BriefsPage from './pages/BriefsPage.jsx'
import BridgePage from './pages/BridgePage.jsx'
import AnalyzePage from './pages/AnalyzePage.jsx'
import WorkspacePage from './pages/WorkspacePage.jsx'
import { LoginPage, RegisterPage } from './pages/AuthPages.jsx'

// ---------------------------------------------------------------------------
// Home page
// ---------------------------------------------------------------------------

function HomePage({ stats }) {
  return (
    <div style={{ ...s.page, paddingTop: '48px' }}>
      <div style={{ textAlign: 'center', maxWidth: '600px', margin: '0 auto 48px' }}>
        <div style={{ fontSize: '40px', marginBottom: '16px' }}>⬡</div>
        <h1 style={{ fontSize: '32px', fontWeight: '800', color: '#e0e0e8', margin: '0 0 12px', letterSpacing: '-1px' }}>
          Connectome Explorer
        </h1>
        <p style={{ fontSize: '15px', color: '#6b7280', lineHeight: '1.7', margin: 0 }}>
          Discover hidden connections across the biomedical literature. Powered by AI extraction and graph traversal.
        </p>
      </div>
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '48px' }}>
          {[
            { label: 'Total Papers', value: stats.papers?.total?.toLocaleString(), color: '#7c6af7' },
            { label: 'Extracted', value: (stats.papers?.by_status?.extracted || 0).toLocaleString(), color: '#4ade80' },
            { label: 'Connections', value: stats.connections?.total?.toLocaleString(), color: '#fbbf24' },
            { label: 'Critiques', value: stats.critiques?.toLocaleString(), color: '#60a5fa' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ ...s.card, textAlign: 'center', padding: '24px' }}>
              <div style={{ ...s.bigStat, color }}>{value || '—'}</div>
              <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>{label}</div>
            </div>
          ))}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
        {[
          { to: '/papers', icon: '📄', title: 'Papers', desc: 'Browse and search the full paper library with AI-extracted metadata.' },
          { to: '/connections', icon: '🔗', title: 'Connections', desc: 'Explore cross-paper relationships: contradictions, extensions, and mechanisms.' },
          { to: '/convergences', icon: '🎯', title: 'Convergences', desc: 'Find research hotspots where multiple papers converge on the same findings.' },
          { to: '/gaps', icon: '🔍', title: 'Field Gaps', desc: 'Identify well-connected papers lacking a critique — potential research opportunities.' },
          { to: '/briefs', icon: '🧠', title: 'Intelligence Briefs', desc: 'AI-generated quality assessments for extracted papers.' },
          { to: '/bridge', icon: '🌉', title: 'Bridge Query', desc: 'Find hidden paths connecting two research concepts through the graph.' },
        ].map(({ to, icon, title, desc }) => (
          <Link key={to} to={to} style={{ textDecoration: 'none' }}>
            <div
              style={{ ...s.card, padding: '20px', transition: 'border-color 0.15s' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = '#7c6af7'}
              onMouseLeave={e => e.currentTarget.style.borderColor = '#1e1e2e'}
            >
              <div style={{ fontSize: '24px', marginBottom: '8px' }}>{icon}</div>
              <div style={{ fontSize: '14px', fontWeight: '600', color: '#c4bef8', marginBottom: '6px' }}>{title}</div>
              <div style={{ fontSize: '12px', color: '#6b7280', lineHeight: '1.6' }}>{desc}</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Header (must be inside BrowserRouter for useNavigate)
// ---------------------------------------------------------------------------

function Header({ stats }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <header style={s.header}>
      <div style={{ flexShrink: 0 }}>
        <Link to="/" style={s.logo}>⬡ Decoded</Link>
        <div style={s.tagline}>Literature Connectome</div>
      </div>
      <nav style={s.nav}>
        <NavLink to="/papers" style={navLinkStyle}>Papers</NavLink>
        <NavLink to="/connections" style={navLinkStyle}>Connections</NavLink>
        <NavLink to="/convergences" style={navLinkStyle}>Convergences</NavLink>
        <NavLink to="/gaps" style={navLinkStyle}>Gaps</NavLink>
        <NavLink to="/briefs" style={navLinkStyle}>Briefs</NavLink>
        <NavLink to="/bridge" style={navLinkStyle}>Bridge</NavLink>
        <NavLink to="/analyze" style={navLinkStyle}>Analyze</NavLink>
        {user && <NavLink to="/workspace" style={navLinkStyle}>Workspace</NavLink>}
      </nav>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0 }}>
        {stats && (
          <div style={{ ...s.statsBar, marginLeft: 0 }}>
            <span><b style={{ color: '#7c6af7' }}>{stats.papers?.total?.toLocaleString() || '—'}</b> papers</span>
            <span><b style={{ color: '#fbbf24' }}>{stats.connections?.total?.toLocaleString() || '—'}</b> connections</span>
          </div>
        )}
        {user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '12px', color: '#9991d0' }}>{user.name || user.email}</span>
            <button
              style={{ ...s.btnGhost, padding: '4px 10px', fontSize: '12px' }}
              onClick={() => { logout(); navigate('/') }}
            >Sign out</button>
          </div>
        ) : (
          <Link to="/login" style={{ ...s.btnOutline, fontSize: '12px', padding: '4px 10px' }}>Sign in</Link>
        )}
      </div>
    </header>
  )
}

// ---------------------------------------------------------------------------
// App shell
// ---------------------------------------------------------------------------

function AppInner({ stats }) {
  return (
    <div style={s.app}>
      <Header stats={stats} />
      <Routes>
        <Route path="/" element={<HomePage stats={stats} />} />
        <Route path="/papers" element={<PapersPage />} />
        <Route path="/papers/:id" element={<PaperDetailPage />} />
        <Route path="/paper/:id" element={<PaperDetailPage />} />
        <Route path="/connections" element={<ConnectionsPage />} />
        <Route path="/convergences" element={<ConvergencesPage />} />
        <Route path="/gaps" element={<GapsPage />} />
        <Route path="/briefs" element={<BriefsPage />} />
        <Route path="/bridge" element={<BridgePage />} />
        <Route path="/analyze" element={<AnalyzePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/workspace" element={<WorkspacePage />} />
      </Routes>
    </div>
  )
}

export default function App() {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    fetch(`${API}/stats`).then(r => r.json()).then(setStats).catch(() => {})
  }, [])

  return (
    <BrowserRouter>
      <AuthProvider>
        <AppInner stats={stats} />
      </AuthProvider>
    </BrowserRouter>
  )
}

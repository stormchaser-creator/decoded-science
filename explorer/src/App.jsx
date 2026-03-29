import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Link, NavLink, useNavigate } from 'react-router-dom'
import { API, s, useIsMobile } from './shared.js'
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
import ExplorePage from './pages/ExplorePage.jsx'
import WorkspacePage from './pages/WorkspacePage.jsx'
import { LoginPage, RegisterPage } from './pages/AuthPages.jsx'
import AboutPage from './pages/AboutPage.jsx'

// ---------------------------------------------------------------------------
// Home page
// ---------------------------------------------------------------------------

function FeaturedBrief({ brief }) {
  const qualityColor = brief.overall_quality === 'high' ? '#4ade80' : '#fbbf24'
  return (
    <Link to={`/papers/${brief.paper_id}`} style={{ textDecoration: 'none' }}>
      <div
        style={{ ...s.card, padding: '16px', transition: 'border-color 0.15s' }}
        onMouseEnter={e => e.currentTarget.style.borderColor = '#7c6af7'}
        onMouseLeave={e => e.currentTarget.style.borderColor = '#1e1e2e'}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
          <div style={{ fontSize: '13px', fontWeight: '600', color: '#c4bef8', lineHeight: '1.4', flex: 1 }}>
            {brief.paper_title}
          </div>
          {brief.overall_quality && (
            <div style={{ fontSize: '11px', fontWeight: '700', color: qualityColor, flexShrink: 0, textTransform: 'uppercase' }}>
              {brief.overall_quality}
            </div>
          )}
        </div>
        {brief.brief && (
          <p style={{ fontSize: '12px', color: '#6b7280', margin: '6px 0 0', lineHeight: '1.5', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
            {brief.brief}
          </p>
        )}
      </div>
    </Link>
  )
}

function HomePage({ stats, featuredBriefs }) {
  const isMobile = useIsMobile()
  return (
    <div style={{ ...s.page, paddingTop: isMobile ? '24px' : '48px' }}>
      <div style={{ textAlign: 'center', maxWidth: '600px', margin: `0 auto ${isMobile ? '32px' : '48px'}` }}>
        <div style={{ fontSize: isMobile ? '32px' : '40px', marginBottom: '16px' }}>⬡</div>
        <h1 style={{ fontSize: isMobile ? '24px' : '32px', fontWeight: '800', color: '#e0e0e8', margin: '0 0 12px', letterSpacing: '-1px' }}>
          Connectome Explorer
        </h1>
        <p style={{ fontSize: '15px', color: '#6b7280', lineHeight: '1.7', margin: 0 }}>
          Discover hidden connections across the biomedical literature. Powered by AI extraction and graph traversal.
        </p>
      </div>
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: isMobile ? '10px' : '16px', marginBottom: isMobile ? '24px' : '48px' }}>
          {[
            { label: 'Total Papers', value: stats.papers?.total?.toLocaleString(), color: '#7c6af7' },
            { label: 'Connections', value: stats.connections?.total?.toLocaleString(), color: '#fbbf24' },
            { label: 'Claims Extracted', value: stats.claims?.toLocaleString(), color: '#4ade80' },
            { label: 'Intelligence Briefs', value: stats.critiques?.toLocaleString(), color: '#60a5fa' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ ...s.card, textAlign: 'center', padding: isMobile ? '16px 12px' : '24px' }}>
              <div style={{ ...s.bigStat, color, fontSize: isMobile ? '22px' : '28px' }}>{value || '—'}</div>
              <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>{label}</div>
            </div>
          ))}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : '1fr 1fr 1fr', gap: isMobile ? '10px' : '16px', marginBottom: isMobile ? '24px' : '48px' }}>
        {[
          { to: '/papers', icon: '📄', title: 'Papers', desc: 'Browse and search the full paper library with AI-extracted metadata.' },
          { to: '/explore', icon: '⬡', title: 'Graph Explorer', desc: 'Interactive force-directed graph of paper connections, colored by discipline.' },
          { to: '/connections', icon: '🔗', title: 'Connections', desc: 'Explore cross-paper relationships: contradictions, extensions, and mechanisms.' },
          { to: '/convergences', icon: '🎯', title: 'Convergences', desc: 'Find research hotspots where multiple papers converge on the same findings.' },
          { to: '/briefs', icon: '🧠', title: 'Intelligence Briefs', desc: 'AI-generated quality assessments for extracted papers.' },
          { to: '/bridge', icon: '🌉', title: 'Bridge Query', desc: 'Find hidden paths connecting two research concepts through the graph.' },
        ].map(({ to, icon, title, desc }) => (
          <Link key={to} to={to} style={{ textDecoration: 'none' }}>
            <div
              style={{ ...s.card, padding: isMobile ? '14px' : '20px', transition: 'border-color 0.15s' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = '#7c6af7'}
              onMouseLeave={e => e.currentTarget.style.borderColor = '#1e1e2e'}
            >
              <div style={{ fontSize: isMobile ? '18px' : '24px', marginBottom: '6px' }}>{icon}</div>
              <div style={{ fontSize: isMobile ? '12px' : '14px', fontWeight: '600', color: '#c4bef8', marginBottom: '4px' }}>{title}</div>
              {!isMobile && <div style={{ fontSize: '12px', color: '#6b7280', lineHeight: '1.6' }}>{desc}</div>}
            </div>
          </Link>
        ))}
      </div>

      {featuredBriefs && featuredBriefs.length > 0 && (
        <div style={{ marginBottom: '48px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h2 style={{ fontSize: isMobile ? '14px' : '16px', fontWeight: '700', color: '#e0e0e8', margin: 0 }}>Featured Intelligence Briefs</h2>
            <Link to="/briefs?quality=high" style={{ fontSize: '12px', color: '#7c6af7', textDecoration: 'none' }}>View all →</Link>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: '12px' }}>
            {featuredBriefs.slice(0, isMobile ? 2 : 4).map((b, i) => (
              <FeaturedBrief key={b.id || i} brief={b} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Header (must be inside BrowserRouter for useNavigate)
// ---------------------------------------------------------------------------

const NAV_LINKS = [
  { to: '/papers', label: 'Papers' },
  { to: '/explore', label: 'Graph' },
  { to: '/connections', label: 'Connections' },
  { to: '/convergences', label: 'Convergences' },
  { to: '/briefs', label: 'Briefs' },
  { to: '/bridge', label: 'Bridge' },
  { to: '/analyze', label: 'Analyze' },
  { to: '/about', label: 'About' },
]

function Header({ stats }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header style={{ ...s.header, flexWrap: 'wrap', padding: isMobile ? '10px 16px' : '12px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: isMobile ? '100%' : 'auto' }}>
        <div style={{ flexShrink: 0 }}>
          <Link to="/" style={s.logo} onClick={() => setMenuOpen(false)}>⬡ Decoded</Link>
          {!isMobile && <div style={s.tagline}>Literature Connectome</div>}
        </div>
        {isMobile && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {user ? (
              <button style={{ ...s.btnGhost, padding: '4px 10px', fontSize: '12px' }} onClick={() => { logout(); navigate('/'); setMenuOpen(false) }}>Sign out</button>
            ) : (
              <Link to="/login" style={{ ...s.btnOutline, fontSize: '12px', padding: '4px 10px' }} onClick={() => setMenuOpen(false)}>Sign in</Link>
            )}
            <button
              onClick={() => setMenuOpen(v => !v)}
              style={{ background: 'none', border: '1px solid #1e1e2e', borderRadius: '6px', padding: '6px 10px', cursor: 'pointer', color: '#9991d0', fontSize: '16px', lineHeight: 1 }}
              aria-label="Toggle menu"
            >
              {menuOpen ? '✕' : '☰'}
            </button>
          </div>
        )}
      </div>

      {/* Desktop nav */}
      {!isMobile && (
        <nav style={s.nav}>
          {NAV_LINKS.map(({ to, label }) => (
            <NavLink key={to} to={to} style={navLinkStyle}>{label}</NavLink>
          ))}
          {user && <NavLink to="/workspace" style={navLinkStyle}>Workspace</NavLink>}
        </nav>
      )}

      {/* Desktop right side */}
      {!isMobile && (
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
              <button style={{ ...s.btnGhost, padding: '4px 10px', fontSize: '12px' }} onClick={() => { logout(); navigate('/') }}>Sign out</button>
            </div>
          ) : (
            <Link to="/login" style={{ ...s.btnOutline, fontSize: '12px', padding: '4px 10px' }}>Sign in</Link>
          )}
        </div>
      )}

      {/* Mobile dropdown nav */}
      {isMobile && menuOpen && (
        <nav style={{ width: '100%', borderTop: '1px solid #1e1e2e', paddingTop: '10px', marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {NAV_LINKS.map(({ to, label }) => (
            <NavLink key={to} to={to} style={navLinkStyle} onClick={() => setMenuOpen(false)}>{label}</NavLink>
          ))}
          {user && <NavLink to="/workspace" style={navLinkStyle} onClick={() => setMenuOpen(false)}>Workspace</NavLink>}
          {stats && (
            <div style={{ padding: '8px 12px', fontSize: '11px', color: '#6b7280', borderTop: '1px solid #1e1e2e', marginTop: '6px' }}>
              <b style={{ color: '#7c6af7' }}>{stats.papers?.total?.toLocaleString() || '—'}</b> papers · <b style={{ color: '#fbbf24' }}>{stats.connections?.total?.toLocaleString() || '—'}</b> connections
            </div>
          )}
        </nav>
      )}
    </header>
  )
}

// ---------------------------------------------------------------------------
// App shell
// ---------------------------------------------------------------------------

function AppInner({ stats, featuredBriefs }) {
  return (
    <div style={s.app}>
      <Header stats={stats} />
      <Routes>
        <Route path="/" element={<HomePage stats={stats} featuredBriefs={featuredBriefs} />} />
        <Route path="/papers" element={<PapersPage />} />
        <Route path="/papers/:id" element={<PaperDetailPage />} />
        <Route path="/paper/:id" element={<PaperDetailPage />} />
        <Route path="/connections" element={<ConnectionsPage />} />
        <Route path="/convergences" element={<ConvergencesPage />} />
        <Route path="/gaps" element={<GapsPage />} />
        <Route path="/briefs" element={<BriefsPage />} />
        <Route path="/bridge" element={<BridgePage />} />
        <Route path="/analyze" element={<AnalyzePage />} />
        <Route path="/explore" element={<ExplorePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/workspace" element={<WorkspacePage />} />
        <Route path="/about" element={<AboutPage />} />
      </Routes>
    </div>
  )
}

export default function App() {
  const [stats, setStats] = useState(null)
  const [featuredBriefs, setFeaturedBriefs] = useState(null)

  useEffect(() => {
    fetch(`${API}/v1/stats`).then(r => r.json()).then(setStats).catch(() => {})
    fetch(`${API}/critiques?limit=5&quality=high`).then(r => r.json())
      .then(d => setFeaturedBriefs(d.critiques || []))
      .catch(() => {})
  }, [])

  return (
    <BrowserRouter>
      <AuthProvider>
        <AppInner stats={stats} featuredBriefs={featuredBriefs} />
      </AuthProvider>
    </BrowserRouter>
  )
}

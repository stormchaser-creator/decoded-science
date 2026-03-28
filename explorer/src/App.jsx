import React, { useState, useEffect, useCallback, createContext, useContext } from 'react'
import { BrowserRouter, Routes, Route, Link, NavLink, useParams, useNavigate } from 'react-router-dom'

const API = import.meta.env.VITE_API_URL || '/api'

// ---------------------------------------------------------------------------
// Auth context
// ---------------------------------------------------------------------------

const AuthContext = createContext(null)

function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('decoded_user')) } catch { return null }
  })
  const [token, setToken] = useState(() => localStorage.getItem('decoded_token') || null)

  const login = (u, t) => {
    setUser(u)
    setToken(t)
    localStorage.setItem('decoded_user', JSON.stringify(u))
    localStorage.setItem('decoded_token', t)
  }
  const logout = () => {
    setUser(null)
    setToken(null)
    localStorage.removeItem('decoded_user')
    localStorage.removeItem('decoded_token')
  }

  return <AuthContext.Provider value={{ user, token, login, logout }}>{children}</AuthContext.Provider>
}

function useAuth() { return useContext(AuthContext) }

function authFetch(url, token, opts = {}) {
  return fetch(url, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  })
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const s = {
  app: { minHeight: '100vh', background: '#0a0a0f', color: '#e0e0e8', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  header: { borderBottom: '1px solid #1e1e2e', padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '20px', background: '#0d0d18', position: 'sticky', top: 0, zIndex: 100 },
  logo: { fontSize: '18px', fontWeight: '700', color: '#7c6af7', letterSpacing: '-0.5px', textDecoration: 'none', flexShrink: 0 },
  tagline: { fontSize: '11px', color: '#6b7280', marginTop: '1px' },
  nav: { display: 'flex', gap: '2px', flexWrap: 'wrap' },
  navLink: { padding: '5px 12px', borderRadius: '6px', fontSize: '13px', color: '#9991d0', textDecoration: 'none', transition: 'background 0.15s' },
  navLinkActive: { background: '#1e1e2e', color: '#c4bef8' },
  statsBar: { display: 'flex', gap: '20px', marginLeft: 'auto', fontSize: '12px', color: '#6b7280', flexShrink: 0 },
  page: { padding: '24px', maxWidth: '1100px', margin: '0 auto' },
  sectionTitle: { fontSize: '11px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '14px' },
  card: { background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '8px', padding: '16px', marginBottom: '10px' },
  paperLink: { fontSize: '14px', fontWeight: '600', color: '#7c6af7', lineHeight: '1.4', textDecoration: 'none' },
  paperMeta: { fontSize: '12px', color: '#6b7280', marginTop: '4px' },
  tag: { display: 'inline-block', background: '#1e1e2e', borderRadius: '4px', padding: '2px 8px', fontSize: '11px', color: '#9991d0', marginRight: '6px', marginTop: '4px' },
  tagGreen: { background: '#0d2010', color: '#4ade80' },
  tagYellow: { background: '#1a1500', color: '#fbbf24' },
  tagRed: { background: '#1a0808', color: '#f87171' },
  tagBlue: { background: '#0a0a20', color: '#60a5fa' },
  tagPurple: { background: '#140a20', color: '#c084fc' },
  input: { width: '100%', background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '6px', padding: '8px 12px', color: '#e0e0e8', fontSize: '13px', outline: 'none', marginBottom: '8px', boxSizing: 'border-box' },
  btn: { background: '#7c6af7', color: '#fff', border: 'none', borderRadius: '6px', padding: '8px 16px', fontSize: '13px', cursor: 'pointer' },
  btnOutline: { background: 'transparent', color: '#7c6af7', border: '1px solid #7c6af7', borderRadius: '6px', padding: '6px 12px', fontSize: '12px', cursor: 'pointer', textDecoration: 'none', display: 'inline-block' },
  btnGhost: { background: '#1e1e2e', color: '#9991d0', border: 'none', borderRadius: '6px', padding: '8px 16px', fontSize: '13px', cursor: 'pointer' },
  errorBanner: { background: '#1a0808', border: '1px solid #4a1010', borderRadius: '8px', padding: '12px', color: '#f87171', fontSize: '13px', marginBottom: '16px' },
  successBanner: { background: '#0d2010', border: '1px solid #1a4020', borderRadius: '8px', padding: '12px', color: '#4ade80', fontSize: '13px', marginBottom: '16px' },
  connArrow: { display: 'flex', alignItems: 'flex-start', gap: '8px', flexWrap: 'wrap' },
  strength: { height: '4px', borderRadius: '2px', background: '#1e1e2e', marginTop: '8px', overflow: 'hidden' },
  strengthBar: { height: '4px', borderRadius: '2px', background: '#7c6af7' },
  twoCol: { display: 'grid', gridTemplateColumns: '260px 1fr', height: 'calc(100vh - 57px)' },
  sidebar: { borderRight: '1px solid #1e1e2e', padding: '20px', overflowY: 'auto', background: '#0d0d18' },
  content: { padding: '24px', overflowY: 'auto' },
  formCard: { background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '10px', padding: '32px', maxWidth: '420px', margin: '60px auto' },
  formTitle: { fontSize: '22px', fontWeight: '700', color: '#e0e0e8', marginBottom: '6px' },
  formSub: { fontSize: '13px', color: '#6b7280', marginBottom: '24px' },
  label: { display: 'block', fontSize: '12px', color: '#9991d0', marginBottom: '4px', fontWeight: '500' },
  paginationRow: { display: 'flex', alignItems: 'center', gap: '8px', padding: '16px 0', fontSize: '13px', color: '#6b7280' },
  bigStat: { fontSize: '28px', fontWeight: '700', color: '#7c6af7' },
  gridTwo: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' },
}

const TYPE_COLORS = {
  contradicts: s.tagRed,
  extends: s.tagGreen,
  mechanism_for: s.tagBlue,
  shares_target: s.tagPurple,
  methodological_parallel: s.tag,
  convergent_evidence: s.tagYellow,
}

// ---------------------------------------------------------------------------
// Shared components
// ---------------------------------------------------------------------------

function TypeTag({ type }) {
  const color = TYPE_COLORS[type] || s.tag
  return <span style={{ ...s.tag, ...color }}>{type?.replace(/_/g, ' ')}</span>
}

function StrengthBar({ confidence, novelty }) {
  return (
    <div>
      <div style={s.strength}>
        <div style={{ ...s.strengthBar, width: `${(confidence || 0) * 100}%` }} />
      </div>
      <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
        Confidence: {((confidence || 0) * 100).toFixed(0)}%
        {novelty != null && ` · Novelty: ${(novelty * 100).toFixed(0)}%`}
      </div>
    </div>
  )
}

function Loading() {
  return <div style={{ color: '#6b7280', fontSize: '13px', padding: '32px 0' }}>Loading…</div>
}

function ErrorMsg({ msg }) {
  return <div style={s.errorBanner}>{msg}</div>
}

function navLinkStyle({ isActive }) {
  return isActive ? { ...s.navLink, ...s.navLinkActive } : s.navLink
}

// ---------------------------------------------------------------------------
// Header
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
            <button style={{ ...s.btnGhost, padding: '4px 10px', fontSize: '12px' }} onClick={() => { logout(); navigate('/') }}>
              Sign out
            </button>
          </div>
        ) : (
          <Link to="/login" style={{ ...s.btnOutline, fontSize: '12px', padding: '4px 10px' }}>Sign in</Link>
        )}
      </div>
    </header>
  )
}

// ---------------------------------------------------------------------------
// Home / landing
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
            { label: 'Extracted', value: (stats.papers?.by_status?.extracted || stats.papers?.by_status?.connected || 0).toLocaleString(), color: '#4ade80' },
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
// Papers page (with pagination)
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50

function PapersPage() {
  const [papers, setPapers] = useState([])
  const [searchQ, setSearchQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [skip, setSkip] = useState(0)
  const [total, setTotal] = useState(0)
  const [isSearch, setIsSearch] = useState(false)

  const loadPapers = useCallback(async (q = '', offset = 0) => {
    setLoading(true)
    setError(null)
    try {
      let data
      if (q) {
        const url = `${API}/search?q=${encodeURIComponent(q)}&limit=${PAGE_SIZE}`
        data = await fetch(url).then(r => r.json())
        setPapers(data.results || [])
        setTotal(data.count || 0)
        setIsSearch(true)
      } else {
        const url = `${API}/papers?limit=${PAGE_SIZE}&skip=${offset}&status=extracted`
        data = await fetch(url).then(r => r.json())
        setPapers(data.papers || [])
        setTotal(data.total || 0)
        setIsSearch(false)
      }
    } catch {
      setError('Cannot reach Decoded API.')
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadPapers('', skip) }, [skip])

  const handleSearch = () => { setSkip(0); loadPapers(searchQ, 0) }
  const handleClear = () => { setSearchQ(''); setSkip(0); loadPapers('', 0) }

  return (
    <div style={s.twoCol}>
      <aside style={s.sidebar}>
        <div style={s.sectionTitle}>Search Papers</div>
        <input
          style={s.input}
          placeholder="e.g. IL-6 inflammation sleep"
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
        />
        <button style={{ ...s.btn, width: '100%' }} onClick={handleSearch}>
          {loading ? 'Searching…' : 'Search'}
        </button>
        <button style={{ ...s.btnGhost, marginTop: '8px', width: '100%' }} onClick={handleClear}>
          Clear / Load All
        </button>
        {!isSearch && total > 0 && (
          <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '16px' }}>
            Showing {skip + 1}–{Math.min(skip + PAGE_SIZE, total)} of {total}
          </div>
        )}
      </aside>
      <main style={s.content}>
        {error && <ErrorMsg msg={error} />}
        <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '14px' }}>
          {loading ? 'Loading…' : isSearch ? `${papers.length} results` : `${total} extracted papers`}
        </div>
        {papers.map(p => (
          <Link key={p.id} to={`/papers/${p.id}`} style={{ textDecoration: 'none' }}>
            <div
              style={s.card}
              onMouseEnter={e => e.currentTarget.style.borderColor = '#7c6af7'}
              onMouseLeave={e => e.currentTarget.style.borderColor = '#1e1e2e'}
            >
              <div style={s.paperLink}>{p.title}</div>
              <div style={s.paperMeta}>
                {p.journal && <span>{p.journal} · </span>}
                {p.published_date && <span>{String(p.published_date).slice(0, 4)}</span>}
              </div>
              <div>
                <span style={{ ...s.tag, ...(p.status === 'extracted' || p.status === 'connected' ? s.tagGreen : {}) }}>
                  {p.status}
                </span>
                {p.connection_count > 0 && (
                  <span style={{ ...s.tag, ...s.tagYellow }}>{p.connection_count} connections</span>
                )}
                {p.critique_quality != null && (
                  <span style={{ ...s.tag, ...s.tagBlue }}>quality {p.critique_quality}/10</span>
                )}
              </div>
            </div>
          </Link>
        ))}
        {!isSearch && total > PAGE_SIZE && (
          <div style={s.paginationRow}>
            <button
              style={{ ...s.btnOutline, opacity: skip === 0 ? 0.4 : 1 }}
              disabled={skip === 0}
              onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
            >← Prev</button>
            <span>Page {Math.floor(skip / PAGE_SIZE) + 1} of {Math.ceil(total / PAGE_SIZE)}</span>
            <button
              style={{ ...s.btnOutline, opacity: skip + PAGE_SIZE >= total ? 0.4 : 1 }}
              disabled={skip + PAGE_SIZE >= total}
              onClick={() => setSkip(skip + PAGE_SIZE)}
            >Next →</button>
          </div>
        )}
      </main>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Paper detail page (with entities + claims)
// ---------------------------------------------------------------------------

function parseJsonField(val) {
  if (!val) return []
  if (Array.isArray(val)) return val
  if (typeof val === 'string') {
    try { return JSON.parse(val) } catch { return [] }
  }
  return []
}

function PaperDetailPage() {
  const { id } = useParams()
  const [paper, setPaper] = useState(null)
  const [connections, setConnections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showEntities, setShowEntities] = useState(false)
  const [showClaims, setShowClaims] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetch(`${API}/papers/${id}`).then(r => r.json()),
      fetch(`${API}/papers/${id}/connections`).then(r => r.json()),
    ]).then(([p, c]) => {
      setPaper(p)
      setConnections(c.connections || [])
      setLoading(false)
    }).catch(() => {
      setError('Failed to load paper.')
      setLoading(false)
    })
  }, [id])

  if (loading) return <div style={s.page}><Loading /></div>
  if (error || !paper) return <div style={s.page}><ErrorMsg msg={error || 'Paper not found'} /></div>

  const entities = parseJsonField(paper.entities)
  const claims = parseJsonField(paper.claims)
  const mechanisms = parseJsonField(paper.mechanisms)

  return (
    <div style={s.page}>
      <Link to="/papers" style={s.btnOutline}>← Back to papers</Link>
      <div style={{ ...s.card, marginTop: '16px' }}>
        <h1 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '8px', lineHeight: '1.4', color: '#e0e0e8' }}>
          {paper.title}
        </h1>
        <div style={s.paperMeta}>
          {paper.journal && <span>{paper.journal} · </span>}
          {paper.published_date && <span>{paper.published_date?.slice?.(0, 4)} · </span>}
          {paper.doi && (
            <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noopener" style={{ color: '#7c6af7' }}>
              DOI ↗
            </a>
          )}
        </div>
        <div style={{ marginTop: '8px' }}>
          <span style={{ ...s.tag, ...(paper.status === 'extracted' || paper.status === 'connected' ? s.tagGreen : {}) }}>
            {paper.status}
          </span>
          {paper.study_design && <span style={s.tag}>{paper.study_design}</span>}
          {paper.sample_size && <span style={s.tag}>n={paper.sample_size}</span>}
        </div>
        {paper.abstract && (
          <p style={{ fontSize: '13px', color: '#a0a0b8', marginTop: '16px', lineHeight: '1.7' }}>
            {paper.abstract}
          </p>
        )}
        {paper.key_findings && (
          <div style={{ marginTop: '12px' }}>
            <div style={{ fontSize: '11px', color: '#6b7280', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>Key Findings</div>
            <p style={{ fontSize: '13px', color: '#a0a0b8', lineHeight: '1.7', margin: 0 }}>
              {typeof paper.key_findings === 'string' ? paper.key_findings : JSON.stringify(paper.key_findings)}
            </p>
          </div>
        )}
      </div>

      {entities.length > 0 && (
        <div style={{ ...s.card, marginTop: '12px' }}>
          <div
            style={{ ...s.sectionTitle, cursor: 'pointer', marginBottom: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
            onClick={() => setShowEntities(v => !v)}
          >
            <span>Entities ({entities.length})</span>
            <span style={{ fontSize: '16px', color: '#7c6af7' }}>{showEntities ? '−' : '+'}</span>
          </div>
          {showEntities && (
            <div style={{ marginTop: '12px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {entities.map((e, i) => (
                <span key={i} style={{ ...s.tag, ...s.tagPurple, marginTop: 0 }}>
                  {typeof e === 'string' ? e : (e.name || e.text || JSON.stringify(e))}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {claims.length > 0 && (
        <div style={{ ...s.card, marginTop: '12px' }}>
          <div
            style={{ ...s.sectionTitle, cursor: 'pointer', marginBottom: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
            onClick={() => setShowClaims(v => !v)}
          >
            <span>Claims ({claims.length})</span>
            <span style={{ fontSize: '16px', color: '#7c6af7' }}>{showClaims ? '−' : '+'}</span>
          </div>
          {showClaims && (
            <div style={{ marginTop: '12px' }}>
              {claims.map((c, i) => (
                <div key={i} style={{ fontSize: '13px', color: '#a0a0b8', lineHeight: '1.6', padding: '8px 0', borderBottom: i < claims.length - 1 ? '1px solid #1e1e2e' : 'none' }}>
                  {typeof c === 'string' ? c : (c.text || c.claim || JSON.stringify(c))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {mechanisms.length > 0 && (
        <div style={{ ...s.card, marginTop: '12px' }}>
          <div style={{ ...s.sectionTitle, marginBottom: '8px' }}>Mechanisms ({mechanisms.length})</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {mechanisms.map((m, i) => (
              <span key={i} style={{ ...s.tag, ...s.tagBlue, marginTop: 0 }}>
                {typeof m === 'string' ? m : (m.name || m.text || JSON.stringify(m))}
              </span>
            ))}
          </div>
        </div>
      )}

      {connections.length > 0 && (
        <div style={{ marginTop: '20px' }}>
          <div style={s.sectionTitle}>Discovered Connections ({connections.length})</div>
          {connections.map((c, i) => {
            const isA = String(c.paper_a_id) === String(id)
            const otherId = isA ? c.paper_b_id : c.paper_a_id
            const otherTitle = isA ? c.paper_b_title : c.paper_a_title
            return (
              <div key={c.id || i} style={s.card}>
                <div style={s.connArrow}>
                  <span style={{ fontSize: '12px', color: '#6b7280', paddingTop: '2px' }}>This paper →</span>
                  <TypeTag type={c.connection_type} />
                  <span style={{ fontSize: '12px', color: '#6b7280', paddingTop: '2px' }}>→</span>
                  <Link to={`/papers/${otherId}`} style={s.paperLink}>{otherTitle}</Link>
                </div>
                {c.description && (
                  <p style={{ fontSize: '13px', color: '#a0a0b8', marginTop: '8px', lineHeight: '1.6' }}>
                    {c.description}
                  </p>
                )}
                <StrengthBar confidence={c.confidence} novelty={c.novelty_score} />
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Connections page
// ---------------------------------------------------------------------------

const CONNECTION_TYPES = [
  'contradicts', 'extends', 'mechanism_for',
  'shares_target', 'methodological_parallel', 'convergent_evidence',
]

function ConnectionsPage() {
  const [connections, setConnections] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [typeFilter, setTypeFilter] = useState('')
  const [minConf, setMinConf] = useState(0.5)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: 100, min_confidence: minConf })
      if (typeFilter) params.set('connection_type', typeFilter)
      const data = await fetch(`${API}/connections?${params}`).then(r => r.json())
      setConnections(data.connections || [])
      setTotal(data.total || 0)
    } catch {
      setError('Cannot load connections.')
    }
    setLoading(false)
  }, [typeFilter, minConf])

  useEffect(() => { load() }, [load])

  return (
    <div style={s.twoCol}>
      <aside style={s.sidebar}>
        <div style={s.sectionTitle}>Filter</div>
        <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '6px' }}>Connection Type</div>
        <select style={{ ...s.input, cursor: 'pointer' }} value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
          <option value="">All types</option>
          {CONNECTION_TYPES.map(t => (
            <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
          ))}
        </select>
        <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '6px' }}>
          Min Confidence: {(minConf * 100).toFixed(0)}%
        </div>
        <input
          type="range" min="0" max="1" step="0.05"
          value={minConf}
          onChange={e => setMinConf(parseFloat(e.target.value))}
          style={{ width: '100%', marginBottom: '16px', cursor: 'pointer' }}
        />
        <div style={{ fontSize: '12px', color: '#6b7280' }}>
          Showing {connections.length} of {total}
        </div>
      </aside>
      <main style={s.content}>
        {error && <ErrorMsg msg={error} />}
        {loading && <Loading />}
        {!loading && connections.map((c, i) => (
          <div key={c.id || i} style={s.card}>
            <div style={s.connArrow}>
              <Link to={`/papers/${c.paper_a_id}`} style={s.paperLink}>{c.paper_a_title || 'Unknown paper'}</Link>
              <span style={{ fontSize: '12px', color: '#6b7280', paddingTop: '2px', flexShrink: 0 }}>→</span>
              <TypeTag type={c.connection_type} />
              <span style={{ fontSize: '12px', color: '#6b7280', paddingTop: '2px', flexShrink: 0 }}>→</span>
              <Link to={`/papers/${c.paper_b_id}`} style={s.paperLink}>{c.paper_b_title || 'Unknown paper'}</Link>
            </div>
            {c.description && (
              <p style={{ fontSize: '13px', color: '#a0a0b8', marginTop: '8px', lineHeight: '1.6' }}>
                {c.description}
              </p>
            )}
            <StrengthBar confidence={c.confidence} novelty={c.novelty_score} />
          </div>
        ))}
      </main>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Convergence Dashboard
// ---------------------------------------------------------------------------

function ConvergencesPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [minConf, setMinConf] = useState(0.7)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetch(`${API}/connections/convergences?min_confidence=${minConf}&limit=50`).then(r => r.json())
      setItems(data.convergences || [])
    } catch {
      setError('Cannot load convergences.')
    }
    setLoading(false)
  }, [minConf])

  useEffect(() => { load() }, [load])

  return (
    <div style={s.twoCol}>
      <aside style={s.sidebar}>
        <div style={s.sectionTitle}>Convergence Zones</div>
        <p style={{ fontSize: '12px', color: '#6b7280', lineHeight: '1.6', marginBottom: '16px' }}>
          Papers at the intersection of multiple high-confidence connections — research convergence zones where evidence accumulates.
        </p>
        <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '6px' }}>
          Min Confidence: {(minConf * 100).toFixed(0)}%
        </div>
        <input
          type="range" min="0.5" max="1" step="0.05"
          value={minConf}
          onChange={e => setMinConf(parseFloat(e.target.value))}
          style={{ width: '100%', marginBottom: '16px', cursor: 'pointer' }}
        />
        <div style={{ fontSize: '12px', color: '#6b7280' }}>{items.length} convergence zones found</div>
      </aside>
      <main style={s.content}>
        {error && <ErrorMsg msg={error} />}
        {loading && <Loading />}
        {!loading && items.length === 0 && (
          <div style={{ fontSize: '13px', color: '#6b7280' }}>No convergence zones at this confidence threshold.</div>
        )}
        {!loading && items.map((item, i) => {
          const avgConf = parseFloat(item.avg_confidence) || 0
          const types = Array.isArray(item.connection_types) ? item.connection_types : []
          return (
            <div key={item.id || i} style={s.card}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                <Link to={`/papers/${item.id}`} style={{ ...s.paperLink, flex: 1 }}>{item.title}</Link>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontSize: '22px', fontWeight: '700', color: '#fbbf24' }}>{item.connection_count}</div>
                  <div style={{ fontSize: '11px', color: '#6b7280' }}>connections</div>
                </div>
              </div>
              <div style={{ marginTop: '8px' }}>
                {types.filter(Boolean).map(t => <TypeTag key={t} type={t} />)}
              </div>
              <div style={s.strength}>
                <div style={{ ...s.strengthBar, width: `${avgConf * 100}%`, background: '#fbbf24' }} />
              </div>
              <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                Avg confidence: {(avgConf * 100).toFixed(0)}%
                {item.doi && (
                  <> · <a href={`https://doi.org/${item.doi}`} target="_blank" rel="noopener" style={{ color: '#7c6af7' }}>DOI ↗</a></>
                )}
              </div>
            </div>
          )
        })}
      </main>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Field Gaps page
// ---------------------------------------------------------------------------

function GapsPage() {
  const [gaps, setGaps] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API}/gaps?limit=50`)
      .then(r => r.json())
      .then(d => { setGaps(d.gaps || []); setLoading(false) })
      .catch(() => { setError('Cannot load gaps.'); setLoading(false) })
  }, [])

  return (
    <div style={s.page}>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 6px' }}>Field Gaps</h2>
        <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>
          Well-connected papers that haven't been critiqued yet — potential research opportunities or areas needing deeper analysis.
        </p>
      </div>
      {error && <ErrorMsg msg={error} />}
      {loading && <Loading />}
      {!loading && gaps.length === 0 && (
        <div style={{ fontSize: '13px', color: '#6b7280' }}>No gaps found — all well-connected papers have been critiqued.</div>
      )}
      {!loading && gaps.map((gap, i) => (
        <div key={gap.id || i} style={s.card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
            <div style={{ flex: 1 }}>
              <Link to={`/papers/${gap.id}`} style={s.paperLink}>{gap.title}</Link>
              <div style={s.paperMeta}>
                {gap.journal && <span>{gap.journal} · </span>}
                {gap.published_date && <span>{String(gap.published_date).slice(0, 4)}</span>}
              </div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontSize: '20px', fontWeight: '700', color: '#f87171' }}>{gap.connection_count}</div>
              <div style={{ fontSize: '11px', color: '#6b7280' }}>connections</div>
            </div>
          </div>
          <div style={{ marginTop: '8px' }}>
            <span style={{ ...s.tag, ...s.tagYellow }}>{gap.connection_count} connections</span>
            <span style={{ ...s.tag, ...s.tagRed }}>no critique</span>
            <span style={{ ...s.tag, ...(gap.status === 'extracted' || gap.status === 'connected' ? s.tagGreen : {}) }}>
              {gap.status}
            </span>
          </div>
          <div style={{ marginTop: '10px' }}>
            <Link to="/analyze" style={{ ...s.btnOutline, fontSize: '11px', padding: '3px 10px', cursor: 'pointer' }}>
              Analyze →
            </Link>
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Intelligence Briefs page
// ---------------------------------------------------------------------------

function BriefsPage() {
  const [briefs, setBriefs] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState({})
  const [skip, setSkip] = useState(0)

  const load = useCallback(async (offset = 0) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetch(`${API}/critiques?limit=20&skip=${offset}`).then(r => r.json())
      setBriefs(data.critiques || [])
      setTotal(data.total || 0)
    } catch {
      setError('Cannot load intelligence briefs.')
    }
    setLoading(false)
  }, [])

  useEffect(() => { load(skip) }, [skip])

  const toggle = id => setExpanded(p => ({ ...p, [id]: !p[id] }))

  return (
    <div style={s.page}>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 6px' }}>Intelligence Briefs</h2>
        <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>
          AI-generated quality assessments and connection summaries for extracted papers. {total > 0 && `${total} total.`}
        </p>
      </div>
      {error && <ErrorMsg msg={error} />}
      {loading && <Loading />}
      {!loading && briefs.length === 0 && (
        <div style={{ fontSize: '13px', color: '#6b7280' }}>No intelligence briefs yet.</div>
      )}
      {!loading && briefs.map((b, i) => {
        const key = b.id || i
        const isOpen = expanded[key]
        const quality = parseFloat(b.overall_quality) || 0
        const confidence = parseFloat(b.confidence_score) || 0
        return (
          <div key={key} style={s.card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
              <div style={{ flex: 1 }}>
                <Link to={`/papers/${b.paper_id}`} style={s.paperLink}>{b.paper_title}</Link>
                <div style={s.paperMeta}>
                  {b.journal && <span>{b.journal} · </span>}
                  {b.published_date && <span>{String(b.published_date).slice(0, 4)} · </span>}
                  {b.created_at && <span>Assessed {b.created_at.slice(0, 10)}</span>}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '12px', flexShrink: 0 }}>
                {quality > 0 && (
                  <div style={{ textAlign: 'center', minWidth: '40px' }}>
                    <div style={{ fontSize: '20px', fontWeight: '700', color: quality >= 7 ? '#4ade80' : quality >= 5 ? '#fbbf24' : '#f87171' }}>
                      {quality.toFixed(0)}
                    </div>
                    <div style={{ fontSize: '10px', color: '#6b7280' }}>quality</div>
                  </div>
                )}
                {confidence > 0 && (
                  <div style={{ textAlign: 'center', minWidth: '40px' }}>
                    <div style={{ fontSize: '20px', fontWeight: '700', color: '#60a5fa' }}>
                      {(confidence * 100).toFixed(0)}%
                    </div>
                    <div style={{ fontSize: '10px', color: '#6b7280' }}>confidence</div>
                  </div>
                )}
              </div>
            </div>

            {b.connections_summary && (
              <p style={{ fontSize: '13px', color: '#a0a0b8', marginTop: '10px', lineHeight: '1.6', marginBottom: 0 }}>
                {b.connections_summary}
              </p>
            )}

            <div style={{ marginTop: '10px' }}>
              <button
                style={{ ...s.btnGhost, padding: '4px 10px', fontSize: '12px' }}
                onClick={() => toggle(key)}
              >
                {isOpen ? 'Hide full brief ↑' : 'Show full brief ↓'}
              </button>
            </div>

            {isOpen && (
              <div style={{ marginTop: '12px', borderTop: '1px solid #1e1e2e', paddingTop: '12px' }}>
                {b.brief && (
                  <p style={{ fontSize: '13px', color: '#a0a0b8', lineHeight: '1.7', whiteSpace: 'pre-wrap', marginTop: 0 }}>
                    {b.brief}
                  </p>
                )}
                {b.strengths && (
                  <div style={{ marginTop: '12px' }}>
                    <div style={{ fontSize: '11px', color: '#4ade80', fontWeight: '600', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Strengths</div>
                    <p style={{ fontSize: '13px', color: '#a0a0b8', margin: 0, lineHeight: '1.6' }}>{b.strengths}</p>
                  </div>
                )}
                {b.weaknesses && (
                  <div style={{ marginTop: '10px' }}>
                    <div style={{ fontSize: '11px', color: '#f87171', fontWeight: '600', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Weaknesses</div>
                    <p style={{ fontSize: '13px', color: '#a0a0b8', margin: 0, lineHeight: '1.6' }}>{b.weaknesses}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
      {total > 20 && (
        <div style={s.paginationRow}>
          <button style={{ ...s.btnOutline, opacity: skip === 0 ? 0.4 : 1 }} disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - 20))}>← Prev</button>
          <span>Page {Math.floor(skip / 20) + 1} of {Math.ceil(total / 20)}</span>
          <button style={{ ...s.btnOutline, opacity: skip + 20 >= total ? 0.4 : 1 }} disabled={skip + 20 >= total} onClick={() => setSkip(skip + 20)}>Next →</button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Bridge page
// ---------------------------------------------------------------------------

function BridgePage() {
  const [bridgeA, setBridgeA] = useState('')
  const [bridgeB, setBridgeB] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const run = async () => {
    if (!bridgeA || !bridgeB) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await fetch(`${API}/bridge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concept_a: bridgeA, concept_b: bridgeB, max_hops: 4 }),
      }).then(r => r.json())
      setResult(data)
    } catch {
      setError('Bridge query failed.')
    }
    setLoading(false)
  }

  return (
    <div style={s.page}>
      <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 6px' }}>Bridge Query</h2>
      <p style={{ fontSize: '13px', color: '#6b7280', marginBottom: '20px' }}>
        Find hidden connections between two research concepts via graph traversal and LLM bridge hypothesis.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '8px', alignItems: 'flex-end', marginBottom: '16px' }}>
        <div>
          <label style={s.label}>Concept A</label>
          <input style={{ ...s.input, marginBottom: 0 }} placeholder="e.g. IL-6" value={bridgeA} onChange={e => setBridgeA(e.target.value)} onKeyDown={e => e.key === 'Enter' && run()} />
        </div>
        <div>
          <label style={s.label}>Concept B</label>
          <input style={{ ...s.input, marginBottom: 0 }} placeholder="e.g. sleep deprivation" value={bridgeB} onChange={e => setBridgeB(e.target.value)} onKeyDown={e => e.key === 'Enter' && run()} />
        </div>
        <button style={s.btn} onClick={run} disabled={loading || !bridgeA || !bridgeB}>
          {loading ? 'Searching…' : 'Find Bridge'}
        </button>
      </div>
      {error && <ErrorMsg msg={error} />}
      {loading && (
        <div style={{ ...s.card, textAlign: 'center', padding: '32px', color: '#6b7280' }}>
          Running graph traversal and LLM bridge analysis… this may take 15–30 seconds.
        </div>
      )}
      {result && (
        <div>
          <div style={{ ...s.card, borderColor: '#2a2040' }}>
            <div style={{ fontWeight: '600', color: '#9991d0', marginBottom: '12px', fontSize: '15px' }}>
              {result.concept_a} ↔ {result.concept_b}
            </div>
            <div style={{ display: 'flex', gap: '16px', marginBottom: '12px', fontSize: '12px', color: '#6b7280', flexWrap: 'wrap' }}>
              <span>🔗 {result.graph_paths_found} graph paths</span>
              <span>📄 {result.papers_a_count} papers on "{result.concept_a}"</span>
              <span>📄 {result.papers_b_count} papers on "{result.concept_b}"</span>
              <span>🔍 {result.similar_papers?.length || 0} similar papers</span>
            </div>
            {result.hypothesis ? (
              <p style={{ fontSize: '14px', color: '#e0e0e8', lineHeight: '1.8', margin: 0 }}>
                {result.hypothesis}
              </p>
            ) : (
              <div style={{ fontSize: '13px', color: '#6b7280' }}>
                No bridge hypothesis generated. Try broader concept terms.
              </div>
            )}
            {result.cost_usd > 0 && (
              <div style={{ fontSize: '11px', color: '#4b4b6b', marginTop: '10px' }}>
                API cost: ${result.cost_usd.toFixed(4)}
              </div>
            )}
          </div>

          {result.graph_paths?.length > 0 && (
            <div style={{ marginTop: '16px' }}>
              <div style={s.sectionTitle}>Graph Paths ({result.graph_paths.length})</div>
              {result.graph_paths.map((path, i) => (
                <div key={i} style={s.card}>
                  <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '8px' }}>
                    {path.hops} hop{path.hops !== 1 ? 's' : ''} · {(path.rel_types || []).join(' → ')}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
                    {(path.path_nodes || []).map((node, j) => (
                      <React.Fragment key={j}>
                        {j > 0 && <span style={{ color: '#4b4b6b', fontSize: '12px' }}>→</span>}
                        <span style={{
                          ...s.tag,
                          ...((node.labels || []).includes('Paper') ? s.tagPurple : s.tagBlue),
                          marginTop: 0
                        }}>
                          {(node.title || node.name || node.text || '?').slice(0, 80)}
                          {(node.title || node.name || node.text || '').length > 80 ? '…' : ''}
                        </span>
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {result.similar_papers?.length > 0 && (
            <div style={{ marginTop: '16px' }}>
              <div style={s.sectionTitle}>Related Papers</div>
              {result.similar_papers.map((p, i) => (
                <div key={i} style={s.card}>
                  <Link to={`/papers/${p.paper_b_id || p.id}`} style={s.paperLink}>
                    {p.paper_b_title || p.title || 'Unknown paper'}
                  </Link>
                  {p.similarity != null && (
                    <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                      Similarity: {(p.similarity * 100).toFixed(0)}%
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Auth pages
// ---------------------------------------------------------------------------

function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const { login } = useAuth()
  const navigate = useNavigate()

  const submit = async e => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Login failed')
      login(data.user, data.token)
      navigate('/workspace')
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }

  return (
    <div style={s.formCard}>
      <div style={s.formTitle}>Sign in</div>
      <div style={s.formSub}>Access your workspace and saved searches.</div>
      {error && <ErrorMsg msg={error} />}
      <form onSubmit={submit}>
        <label style={s.label}>Email</label>
        <input style={s.input} type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} required />
        <label style={s.label}>Password</label>
        <input style={s.input} type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} required />
        <button style={{ ...s.btn, width: '100%', padding: '10px', marginTop: '8px' }} type="submit" disabled={loading}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <div style={{ textAlign: 'center', marginTop: '16px', fontSize: '13px', color: '#6b7280' }}>
        No account? <Link to="/register" style={{ color: '#7c6af7' }}>Create one</Link>
      </div>
    </div>
  )
}

function RegisterPage() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const { login } = useAuth()
  const navigate = useNavigate()

  const submit = async e => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Registration failed')
      login(data.user, data.token)
      navigate('/workspace')
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }

  return (
    <div style={s.formCard}>
      <div style={s.formTitle}>Create account</div>
      <div style={s.formSub}>Save searches, build collections, set up alerts.</div>
      {error && <ErrorMsg msg={error} />}
      <form onSubmit={submit}>
        <label style={s.label}>Name</label>
        <input style={s.input} type="text" placeholder="Your name" value={name} onChange={e => setName(e.target.value)} required />
        <label style={s.label}>Email</label>
        <input style={s.input} type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} required />
        <label style={s.label}>Password</label>
        <input style={s.input} type="password" placeholder="At least 8 characters" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} />
        <button style={{ ...s.btn, width: '100%', padding: '10px', marginTop: '8px' }} type="submit" disabled={loading}>
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <div style={{ textAlign: 'center', marginTop: '16px', fontSize: '13px', color: '#6b7280' }}>
        Already have an account? <Link to="/login" style={{ color: '#7c6af7' }}>Sign in</Link>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Workspace
// ---------------------------------------------------------------------------

function WorkspacePage() {
  const { user, token, logout } = useAuth()
  const navigate = useNavigate()
  const [searches, setSearches] = useState([])
  const [collections, setCollections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [newSearch, setNewSearch] = useState({ name: '', query: '' })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!user) { navigate('/login'); return }
    Promise.all([
      authFetch(`${API}/workspace/searches`, token).then(r => r.json()),
      authFetch(`${API}/workspace/collections`, token).then(r => r.json()),
    ]).then(([sd, cd]) => {
      setSearches(sd.searches || [])
      setCollections(cd.collections || [])
      setLoading(false)
    }).catch(() => {
      setError('Cannot load workspace.')
      setLoading(false)
    })
  }, [user, token])

  const saveSearch = async e => {
    e.preventDefault()
    if (!newSearch.name || !newSearch.query) return
    setSaving(true)
    try {
      const res = await authFetch(`${API}/workspace/searches`, token, {
        method: 'POST',
        body: JSON.stringify({ name: newSearch.name, query: newSearch.query, filters: {} }),
      })
      if (res.ok) {
        const saved = await res.json()
        setSearches(p => [saved, ...p])
        setNewSearch({ name: '', query: '' })
      }
    } catch {}
    setSaving(false)
  }

  const deleteSearch = async id => {
    try {
      await authFetch(`${API}/workspace/searches/${id}`, token, { method: 'DELETE' })
      setSearches(p => p.filter(item => item.id !== id))
    } catch {}
  }

  if (!user) return null

  return (
    <div style={s.page}>
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 4px' }}>Workspace</h2>
        <div style={{ fontSize: '13px', color: '#6b7280' }}>
          Welcome back, {user.name || user.email}
          {user.role && user.role !== 'user' && <span style={{ ...s.tag, ...s.tagPurple, marginLeft: '8px' }}>{user.role}</span>}
        </div>
      </div>
      {error && <ErrorMsg msg={error} />}
      {loading && <Loading />}
      {!loading && (
        <div style={s.gridTwo}>
          <div>
            <div style={s.sectionTitle}>Saved Searches ({searches.length})</div>
            <div style={s.card}>
              <div style={{ fontSize: '13px', color: '#9991d0', marginBottom: '10px', fontWeight: '600' }}>Save a new search</div>
              <form onSubmit={saveSearch}>
                <input style={s.input} placeholder="Search name (e.g. IL-6 studies)" value={newSearch.name} onChange={e => setNewSearch(p => ({ ...p, name: e.target.value }))} />
                <input style={s.input} placeholder="Query terms" value={newSearch.query} onChange={e => setNewSearch(p => ({ ...p, query: e.target.value }))} />
                <button style={s.btn} type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save search'}</button>
              </form>
            </div>
            <div style={{ marginTop: '12px' }}>
              {searches.length === 0 && (
                <div style={{ fontSize: '13px', color: '#6b7280' }}>No saved searches yet.</div>
              )}
              {searches.map(item => (
                <div key={item.id} style={{ background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '8px', padding: '12px', marginBottom: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '13px', fontWeight: '600', color: '#e0e0e8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</div>
                    <div style={{ fontSize: '12px', color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.query}</div>
                  </div>
                  <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                    <Link to={`/papers?q=${encodeURIComponent(item.query)}`} style={{ background: 'transparent', color: '#7c6af7', border: '1px solid #7c6af7', borderRadius: '4px', padding: '3px 8px', fontSize: '11px', cursor: 'pointer', textDecoration: 'none' }}>Run</Link>
                    <button style={{ background: '#1a0808', color: '#f87171', border: '1px solid #4a1010', borderRadius: '4px', padding: '3px 8px', fontSize: '11px', cursor: 'pointer' }} onClick={() => deleteSearch(item.id)}>×</button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div style={s.sectionTitle}>Collections ({collections.length})</div>
            {collections.length === 0 && (
              <div style={{ fontSize: '13px', color: '#6b7280' }}>No collections yet. Collections let you group papers by topic or project.</div>
            )}
            {collections.map(c => (
              <div key={c.id} style={{ background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '8px', padding: '14px', marginBottom: '8px' }}>
                <div style={{ fontSize: '13px', fontWeight: '600', color: '#e0e0e8' }}>{c.name}</div>
                {c.description && <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>{c.description}</div>}
                <div style={{ fontSize: '11px', color: '#4b4b6b', marginTop: '6px' }}>{c.paper_count || 0} papers</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// On-demand DOI Analysis
// ---------------------------------------------------------------------------

function AnalyzePage() {
  const [doi, setDoi] = useState('')
  const [priority, setPriority] = useState(1)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const submit = async e => {
    e.preventDefault()
    if (!doi.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const res = await fetch(`${API}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doi: doi.trim(), priority }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Analysis failed')
      setResult(data)
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }

  return (
    <div style={s.page}>
      <div style={{ maxWidth: '640px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 6px' }}>On-demand Analysis</h2>
        <p style={{ fontSize: '13px', color: '#6b7280', marginBottom: '24px' }}>
          Submit a DOI to trigger full AI extraction and connection discovery. The paper will be fetched, extracted, and added to the connectome.
        </p>
        {error && <ErrorMsg msg={error} />}
        {result && (
          <div style={{ ...s.successBanner, marginBottom: '16px' }}>
            Analysis submitted successfully.
            {result.paper_id && <> · <Link to={`/papers/${result.paper_id}`} style={{ color: '#4ade80', fontWeight: '600' }}>View paper →</Link></>}
          </div>
        )}
        <div style={s.card}>
          <form onSubmit={submit}>
            <label style={s.label}>DOI</label>
            <input
              style={s.input}
              placeholder="10.1016/j.cell.2024.01.001"
              value={doi}
              onChange={e => setDoi(e.target.value)}
            />
            <label style={s.label}>Priority (1 = high, 0 = normal)</label>
            <input
              style={s.input}
              type="number"
              min="0"
              max="10"
              value={priority}
              onChange={e => setPriority(parseInt(e.target.value, 10))}
            />
            <button style={{ ...s.btn, padding: '10px 24px' }} type="submit" disabled={loading || !doi.trim()}>
              {loading ? 'Submitting…' : 'Analyze DOI'}
            </button>
          </form>
        </div>

        {loading && (
          <div style={{ ...s.card, marginTop: '16px', textAlign: 'center', color: '#6b7280', padding: '32px' }}>
            <div style={{ fontSize: '24px', marginBottom: '8px' }}>⚙️</div>
            <div>Analysis queued — runs in background.</div>
            <div style={{ fontSize: '12px', marginTop: '6px', color: '#4b4b6b' }}>Fetching paper, running extraction, discovering connections…</div>
          </div>
        )}

        <div style={{ ...s.card, marginTop: '24px' }}>
          <div style={s.sectionTitle}>How it works</div>
          <div style={{ display: 'grid', gap: '10px' }}>
            {[
              ['1', 'Fetch', 'Paper metadata and full text retrieved from DOI'],
              ['2', 'Extract', 'AI extracts entities, claims, mechanisms, and findings'],
              ['3', 'Connect', 'Graph discovery finds connections to existing papers'],
              ['4', 'Critique', 'Intelligence brief generated with quality assessment'],
            ].map(([n, title, desc]) => (
              <div key={n} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                <div style={{ ...s.tag, ...s.tagPurple, flexShrink: 0, minWidth: '20px', textAlign: 'center', marginTop: 0 }}>{n}</div>
                <div>
                  <span style={{ fontSize: '13px', fontWeight: '600', color: '#9991d0' }}>{title}: </span>
                  <span style={{ fontSize: '13px', color: '#6b7280' }}>{desc}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

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

// AppInner lives inside BrowserRouter so useNavigate works in Header
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

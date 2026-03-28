import React, { useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Link, useParams } from 'react-router-dom'

const API = import.meta.env.VITE_API_URL || '/api'

const s = {
  app: { minHeight: '100vh', background: '#0a0a0f', color: '#e0e0e8', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  header: { borderBottom: '1px solid #1e1e2e', padding: '16px 24px', display: 'flex', alignItems: 'center', gap: '24px', background: '#0d0d18' },
  logo: { fontSize: '20px', fontWeight: '700', color: '#7c6af7', letterSpacing: '-0.5px', textDecoration: 'none' },
  tagline: { fontSize: '13px', color: '#6b7280', marginTop: '2px' },
  nav: { display: 'flex', gap: '4px', marginLeft: '8px' },
  navLink: { padding: '6px 14px', borderRadius: '6px', fontSize: '13px', color: '#9991d0', textDecoration: 'none' },
  statsBar: { display: 'flex', gap: '24px', marginLeft: 'auto', fontSize: '13px', color: '#6b7280' },
  page: { padding: '24px', maxWidth: '1100px', margin: '0 auto' },
  sectionTitle: { fontSize: '11px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '16px' },
  card: { background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '8px', padding: '16px', marginBottom: '12px' },
  paperLink: { fontSize: '14px', fontWeight: '600', color: '#7c6af7', lineHeight: '1.4', textDecoration: 'none' },
  paperMeta: { fontSize: '12px', color: '#6b7280', marginTop: '4px' },
  tag: { display: 'inline-block', background: '#1e1e2e', borderRadius: '4px', padding: '2px 8px', fontSize: '11px', color: '#9991d0', marginRight: '6px', marginTop: '6px' },
  tagGreen: { background: '#0d2010', color: '#4ade80' },
  tagYellow: { background: '#1a1500', color: '#fbbf24' },
  tagRed: { background: '#1a0808', color: '#f87171' },
  tagBlue: { background: '#0a0a20', color: '#60a5fa' },
  tagPurple: { background: '#140a20', color: '#c084fc' },
  input: { width: '100%', background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '6px', padding: '8px 12px', color: '#e0e0e8', fontSize: '13px', outline: 'none', marginBottom: '8px', boxSizing: 'border-box' },
  btn: { background: '#7c6af7', color: '#fff', border: 'none', borderRadius: '6px', padding: '8px 16px', fontSize: '13px', cursor: 'pointer' },
  btnOutline: { background: 'transparent', color: '#7c6af7', border: '1px solid #7c6af7', borderRadius: '6px', padding: '6px 12px', fontSize: '12px', cursor: 'pointer', textDecoration: 'none', display: 'inline-block' },
  errorBanner: { background: '#1a0808', border: '1px solid #4a1010', borderRadius: '8px', padding: '12px', color: '#f87171', fontSize: '13px', marginBottom: '16px' },
  connArrow: { display: 'flex', alignItems: 'flex-start', gap: '8px', flexWrap: 'wrap' },
  strength: { height: '4px', borderRadius: '2px', background: '#1e1e2e', marginTop: '8px', overflow: 'hidden' },
  strengthBar: { height: '4px', borderRadius: '2px', background: '#7c6af7' },
  twoCol: { display: 'grid', gridTemplateColumns: '280px 1fr', height: 'calc(100vh - 65px)' },
  sidebar: { borderRight: '1px solid #1e1e2e', padding: '20px', overflowY: 'auto', background: '#0d0d18' },
  content: { padding: '24px', overflowY: 'auto' },
}

const TYPE_COLORS = {
  contradicts: s.tagRed,
  extends: s.tagGreen,
  mechanism_for: s.tagBlue,
  shares_target: s.tagPurple,
  methodological_parallel: s.tag,
  convergent_evidence: s.tagYellow,
}

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

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

function Header({ stats }) {
  return (
    <header style={s.header}>
      <div>
        <Link to="/" style={s.logo}>⬡ Decoded</Link>
        <div style={s.tagline}>Literature Connectome Explorer</div>
      </div>
      <nav style={s.nav}>
        <Link to="/" style={s.navLink}>Papers</Link>
        <Link to="/connections" style={s.navLink}>Connections</Link>
        <Link to="/bridge" style={s.navLink}>Bridge</Link>
      </nav>
      {stats && (
        <div style={s.statsBar}>
          <span><b style={{ color: '#7c6af7' }}>{stats.papers?.total?.toLocaleString() || '—'}</b> papers</span>
          <span><b style={{ color: '#4ade80' }}>{stats.papers?.by_status?.extracted?.toLocaleString() || '—'}</b> extracted</span>
          <span><b style={{ color: '#fbbf24' }}>{stats.connections?.total?.toLocaleString() || '—'}</b> connections</span>
        </div>
      )}
    </header>
  )
}

// ---------------------------------------------------------------------------
// Papers page
// ---------------------------------------------------------------------------

function PapersPage() {
  const [papers, setPapers] = useState([])
  const [searchQ, setSearchQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const loadPapers = useCallback(async (q = '') => {
    setLoading(true)
    setError(null)
    try {
      const url = q
        ? `${API}/search?q=${encodeURIComponent(q)}&limit=50`
        : `${API}/papers?limit=50&status=extracted`
      const data = await fetch(url).then(r => r.json())
      setPapers(data.results || data.papers || [])
    } catch {
      setError('Cannot reach Decoded API.')
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadPapers() }, [loadPapers])

  return (
    <div style={s.twoCol}>
      <aside style={s.sidebar}>
        <div style={s.sectionTitle}>Search Papers</div>
        <input
          style={s.input}
          placeholder="e.g. IL-6 inflammation sleep"
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && loadPapers(searchQ)}
        />
        <button style={{ ...s.btn, width: '100%' }} onClick={() => loadPapers(searchQ)}>
          {loading ? 'Searching…' : 'Search'}
        </button>
        <button
          style={{ ...s.btn, background: '#1e1e2e', color: '#9991d0', marginTop: '8px', width: '100%' }}
          onClick={() => { setSearchQ(''); loadPapers('') }}
        >
          Clear / Load All
        </button>
      </aside>
      <main style={s.content}>
        {error && <div style={s.errorBanner}>{error}</div>}
        <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '16px' }}>
          {loading ? 'Loading…' : `${papers.length} papers`}
        </div>
        {papers.map(p => (
          <Link key={p.id} to={`/paper/${p.id}`} style={{ textDecoration: 'none' }}>
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
              </div>
            </div>
          </Link>
        ))}
      </main>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Paper detail page
// ---------------------------------------------------------------------------

function PaperDetailPage() {
  const { id } = useParams()
  const [paper, setPaper] = useState(null)
  const [connections, setConnections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

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

  if (loading) return <div style={{ ...s.page, color: '#6b7280' }}>Loading…</div>
  if (error || !paper) return <div style={s.page}><div style={s.errorBanner}>{error || 'Paper not found'}</div></div>

  return (
    <div style={s.page}>
      <Link to="/" style={s.btnOutline}>← Back to papers</Link>
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
      </div>

      {connections.length > 0 && (
        <div>
          <div style={s.sectionTitle}>Discovered Connections ({connections.length})</div>
          {connections.map((c, i) => {
            const isA = c.paper_a_id === id
            const otherId = isA ? c.paper_b_id : c.paper_a_id
            const otherTitle = isA ? c.paper_b_title : c.paper_a_title
            return (
              <div key={c.id || i} style={s.card}>
                <div style={s.connArrow}>
                  <span style={{ fontSize: '12px', color: '#6b7280', paddingTop: '2px' }}>This paper →</span>
                  <TypeTag type={c.connection_type} />
                  <span style={{ fontSize: '12px', color: '#6b7280', paddingTop: '2px' }}>→</span>
                  <Link to={`/paper/${otherId}`} style={s.paperLink}>{otherTitle}</Link>
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
        <select
          style={{ ...s.input, cursor: 'pointer' }}
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
        >
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
        {error && <div style={s.errorBanner}>{error}</div>}
        {loading && <div style={{ color: '#6b7280', fontSize: '13px' }}>Loading…</div>}
        {!loading && connections.map((c, i) => (
          <div key={c.id || i} style={s.card}>
            <div style={s.connArrow}>
              <Link to={`/paper/${c.paper_a_id}`} style={s.paperLink}>
                {c.paper_a_title || 'Unknown paper'}
              </Link>
              <span style={{ fontSize: '12px', color: '#6b7280', paddingTop: '2px', flexShrink: 0 }}>→</span>
              <TypeTag type={c.connection_type} />
              <span style={{ fontSize: '12px', color: '#6b7280', paddingTop: '2px', flexShrink: 0 }}>→</span>
              <Link to={`/paper/${c.paper_b_id}`} style={s.paperLink}>
                {c.paper_b_title || 'Unknown paper'}
              </Link>
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
      <div style={{ fontSize: '18px', fontWeight: '700', color: '#e0e0e8', marginBottom: '8px' }}>
        Bridge Query
      </div>
      <p style={{ fontSize: '13px', color: '#6b7280', marginBottom: '20px' }}>
        Find hidden connections between two research concepts.
      </p>
      <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', marginBottom: '8px' }}>
        <input style={s.input} placeholder="Concept A (e.g. IL-6)" value={bridgeA} onChange={e => setBridgeA(e.target.value)} />
        <input style={s.input} placeholder="Concept B (e.g. sleep deprivation)" value={bridgeB} onChange={e => setBridgeB(e.target.value)} />
        <button style={{ ...s.btn, flexShrink: 0, whiteSpace: 'nowrap' }} onClick={run} disabled={loading}>
          {loading ? 'Searching…' : 'Find Bridge'}
        </button>
      </div>
      {error && <div style={s.errorBanner}>{error}</div>}
      {result && (
        <div style={s.card}>
          <div style={{ fontWeight: '600', marginBottom: '12px', color: '#9991d0' }}>
            {result.concept_a} ↔ {result.concept_b}
          </div>
          {result.hypothesis && (
            <p style={{ fontSize: '13px', color: '#e0e0e8', lineHeight: '1.7' }}>
              {typeof result.hypothesis === 'string' ? result.hypothesis : result.hypothesis?.hypothesis}
            </p>
          )}
          <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '12px' }}>
            {result.graph_paths?.length || 0} graph paths · {result.similar_papers?.length || 0} similar papers
          </div>
        </div>
      )}
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
      <div style={s.app}>
        <Header stats={stats} />
        <Routes>
          <Route path="/" element={<PapersPage />} />
          <Route path="/connections" element={<ConnectionsPage />} />
          <Route path="/paper/:id" element={<PaperDetailPage />} />
          <Route path="/bridge" element={<BridgePage />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

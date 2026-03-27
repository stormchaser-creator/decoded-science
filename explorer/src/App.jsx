import React, { useState, useEffect, useCallback } from 'react'

const API = import.meta.env.VITE_API_URL || '/api'

const styles = {
  app: { minHeight: '100vh', background: '#0a0a0f', color: '#e0e0e8', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  header: { borderBottom: '1px solid #1e1e2e', padding: '16px 24px', display: 'flex', alignItems: 'center', gap: '16px', background: '#0d0d18' },
  logo: { fontSize: '20px', fontWeight: '700', color: '#7c6af7', letterSpacing: '-0.5px' },
  tagline: { fontSize: '13px', color: '#6b7280', marginTop: '2px' },
  main: { display: 'grid', gridTemplateColumns: '320px 1fr', height: 'calc(100vh - 65px)' },
  sidebar: { borderRight: '1px solid #1e1e2e', padding: '20px', overflowY: 'auto', background: '#0d0d18' },
  content: { padding: '24px', overflowY: 'auto' },
  sectionTitle: { fontSize: '11px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '12px' },
  statsGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '24px' },
  statCard: { background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '8px', padding: '12px' },
  statNum: { fontSize: '22px', fontWeight: '700', color: '#7c6af7' },
  statLabel: { fontSize: '11px', color: '#6b7280', marginTop: '2px' },
  searchBox: { width: '100%', background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '8px', padding: '10px 14px', color: '#e0e0e8', fontSize: '14px', outline: 'none', marginBottom: '8px' },
  btn: { background: '#7c6af7', color: '#fff', border: 'none', borderRadius: '6px', padding: '8px 16px', fontSize: '13px', cursor: 'pointer', width: '100%', marginBottom: '8px' },
  btnOutline: { background: 'transparent', color: '#7c6af7', border: '1px solid #7c6af7', borderRadius: '6px', padding: '6px 12px', fontSize: '12px', cursor: 'pointer' },
  paperCard: { background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '8px', padding: '16px', marginBottom: '12px', cursor: 'pointer', transition: 'border-color 0.15s' },
  paperTitle: { fontSize: '14px', fontWeight: '600', color: '#e0e0e8', marginBottom: '6px', lineHeight: '1.4' },
  paperMeta: { fontSize: '12px', color: '#6b7280' },
  tag: { display: 'inline-block', background: '#1e1e2e', borderRadius: '4px', padding: '2px 8px', fontSize: '11px', color: '#9991d0', marginRight: '6px', marginTop: '6px' },
  tagGreen: { background: '#0d2010', color: '#4ade80' },
  tagYellow: { background: '#1a1500', color: '#fbbf24' },
  detail: { background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '8px', padding: '20px', marginBottom: '16px' },
  detailTitle: { fontSize: '18px', fontWeight: '700', marginBottom: '8px', lineHeight: '1.4' },
  input: { width: '100%', background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '6px', padding: '8px 12px', color: '#e0e0e8', fontSize: '13px', outline: 'none', marginBottom: '8px' },
  bridgeResult: { background: '#0d1020', border: '1px solid #2a2a4a', borderRadius: '8px', padding: '16px', marginBottom: '12px' },
  errorBanner: { background: '#1a0808', border: '1px solid #4a1010', borderRadius: '8px', padding: '12px', color: '#f87171', fontSize: '13px', marginBottom: '12px' },
  tab: { padding: '8px 16px', fontSize: '13px', cursor: 'pointer', borderBottom: '2px solid transparent', color: '#6b7280' },
  tabActive: { borderBottomColor: '#7c6af7', color: '#7c6af7' },
}

export default function App() {
  const [stats, setStats] = useState(null)
  const [papers, setPapers] = useState([])
  const [selected, setSelected] = useState(null)
  const [searchQ, setSearchQ] = useState('')
  const [bridgeA, setBridgeA] = useState('')
  const [bridgeB, setBridgeB] = useState('')
  const [bridgeResult, setBridgeResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('papers') // papers | connections | bridge

  useEffect(() => {
    fetch(`${API}/stats`).then(r => r.json()).then(setStats).catch(() => {})
    loadPapers()
  }, [])

  const loadPapers = useCallback(async (q = '') => {
    setLoading(true)
    setError(null)
    try {
      const url = q
        ? `${API}/search?q=${encodeURIComponent(q)}&limit=30`
        : `${API}/papers?limit=30&status=extracted`
      const data = await fetch(url).then(r => r.json())
      setPapers(data.results || data.papers || [])
    } catch (e) {
      setError('Cannot reach Decoded API. Is it running on port 8000?')
    }
    setLoading(false)
  }, [])

  const runBridge = useCallback(async () => {
    if (!bridgeA || !bridgeB) return
    setLoading(true)
    setBridgeResult(null)
    try {
      const data = await fetch(`${API}/bridge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concept_a: bridgeA, concept_b: bridgeB, max_hops: 4 }),
      }).then(r => r.json())
      setBridgeResult(data)
    } catch (e) {
      setError('Bridge query failed.')
    }
    setLoading(false)
  }, [bridgeA, bridgeB])

  const loadPaperDetail = useCallback(async (paperId) => {
    try {
      const [paper, connections] = await Promise.all([
        fetch(`${API}/papers/${paperId}`).then(r => r.json()),
        fetch(`${API}/papers/${paperId}/connections`).then(r => r.json()),
      ])
      setSelected({ ...paper, connections: connections.connections || [] })
    } catch (e) {}
  }, [])

  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <div>
          <div style={styles.logo}>⬡ Decoded</div>
          <div style={styles.tagline}>Literature Connectome Explorer</div>
        </div>
        {stats && (
          <div style={{ display: 'flex', gap: '24px', marginLeft: 'auto', fontSize: '13px', color: '#6b7280' }}>
            <span><b style={{ color: '#7c6af7' }}>{stats.papers?.total?.toLocaleString() || '—'}</b> papers</span>
            <span><b style={{ color: '#4ade80' }}>{stats.papers?.by_status?.extracted?.toLocaleString() || '—'}</b> extracted</span>
            <span><b style={{ color: '#fbbf24' }}>{stats.connections?.total?.toLocaleString() || '—'}</b> connections</span>
          </div>
        )}
      </header>

      <div style={styles.main}>
        {/* Sidebar */}
        <aside style={styles.sidebar}>
          <div style={styles.sectionTitle}>Search Papers</div>
          <input
            style={styles.searchBox}
            placeholder="e.g. IL-6 inflammation sleep"
            value={searchQ}
            onChange={e => setSearchQ(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadPapers(searchQ)}
          />
          <button style={styles.btn} onClick={() => loadPapers(searchQ)}>
            {loading ? 'Searching…' : 'Search'}
          </button>
          <button style={{ ...styles.btn, background: '#1e1e2e', color: '#9991d0' }} onClick={() => { setSearchQ(''); loadPapers('') }}>
            Clear / Load Recent
          </button>

          <div style={{ ...styles.sectionTitle, marginTop: '24px' }}>Bridge Query</div>
          <input style={styles.input} placeholder="Concept A (e.g. IL-6)" value={bridgeA} onChange={e => setBridgeA(e.target.value)} />
          <input style={styles.input} placeholder="Concept B (e.g. sleep)" value={bridgeB} onChange={e => setBridgeB(e.target.value)} />
          <button style={styles.btn} onClick={runBridge}>Find Connections</button>

          {bridgeResult && (
            <div style={styles.bridgeResult}>
              <div style={{ fontSize: '12px', fontWeight: '600', marginBottom: '8px', color: '#9991d0' }}>
                Bridge: {bridgeResult.concept_a} ↔ {bridgeResult.concept_b}
              </div>
              {bridgeResult.hypothesis && (
                <div style={{ fontSize: '12px', color: '#e0e0e8', lineHeight: '1.5' }}>
                  {bridgeResult.hypothesis}
                </div>
              )}
              <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '8px' }}>
                {bridgeResult.graph_paths_found} graph paths · {bridgeResult.similar_papers?.length || 0} similar papers
              </div>
            </div>
          )}

          {stats && (
            <>
              <div style={{ ...styles.sectionTitle, marginTop: '24px' }}>Pipeline Stats</div>
              <div style={styles.statsGrid}>
                {Object.entries(stats.papers?.by_status || {}).slice(0, 6).map(([status, n]) => (
                  <div key={status} style={styles.statCard}>
                    <div style={styles.statNum}>{n}</div>
                    <div style={styles.statLabel}>{status}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </aside>

        {/* Main content */}
        <main style={styles.content}>
          {error && <div style={styles.errorBanner}>{error}</div>}

          {selected ? (
            <div>
              <button style={{ ...styles.btnOutline, marginBottom: '16px' }} onClick={() => setSelected(null)}>
                ← Back to list
              </button>
              <div style={styles.detail}>
                <div style={styles.detailTitle}>{selected.title}</div>
                <div style={styles.paperMeta}>
                  {selected.journal && <span>{selected.journal} · </span>}
                  {selected.published_date && <span>{selected.published_date?.slice?.(0, 4)} · </span>}
                  {selected.doi && <a href={`https://doi.org/${selected.doi}`} target="_blank" rel="noopener" style={{ color: '#7c6af7' }}>DOI</a>}
                </div>
                <div style={{ ...styles.tag, marginTop: '10px' }}>{selected.status}</div>
                {selected.study_design && <div style={styles.tag}>{selected.study_design}</div>}
                {selected.sample_size && <div style={styles.tag}>n={selected.sample_size}</div>}
                {selected.abstract && (
                  <p style={{ fontSize: '13px', color: '#a0a0b8', marginTop: '16px', lineHeight: '1.6' }}>
                    {selected.abstract.slice(0, 600)}{selected.abstract.length > 600 ? '…' : ''}
                  </p>
                )}
              </div>
              {selected.connections?.length > 0 && (
                <div style={styles.detail}>
                  <div style={styles.sectionTitle}>Discovered Connections ({selected.connections.length})</div>
                  {selected.connections.slice(0, 10).map((c, i) => (
                    <div key={i} style={{ padding: '10px 0', borderBottom: '1px solid #1e1e2e', fontSize: '13px' }}>
                      <span style={{ color: '#9991d0' }}>{c.entity_a}</span>
                      <span style={{ color: '#6b7280', margin: '0 8px' }}>→ {c.connection_type} →</span>
                      <span style={{ color: '#9991d0' }}>{c.entity_b}</span>
                      {c.confidence && <span style={{ ...styles.tag, ...styles.tagGreen }}>{(c.confidence * 100).toFixed(0)}%</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <>
              <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '16px' }}>
                {loading ? 'Loading…' : `${papers.length} papers`}
              </div>
              {papers.map(p => (
                <div
                  key={p.id}
                  style={styles.paperCard}
                  onClick={() => loadPaperDetail(p.id)}
                  onMouseEnter={e => e.currentTarget.style.borderColor = '#7c6af7'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = '#1e1e2e'}
                >
                  <div style={styles.paperTitle}>{p.title}</div>
                  <div style={styles.paperMeta}>
                    {p.journal && <span>{p.journal} · </span>}
                    {p.published_date && <span>{String(p.published_date).slice(0, 4)}</span>}
                  </div>
                  <div>
                    <span style={{ ...styles.tag, ...(p.status === 'extracted' || p.status === 'connected' ? styles.tagGreen : {}) }}>
                      {p.status}
                    </span>
                    {p.connection_count > 0 && (
                      <span style={{ ...styles.tag, ...styles.tagYellow }}>{p.connection_count} connections</span>
                    )}
                    {p.doi && <span style={styles.tag}>DOI</span>}
                  </div>
                </div>
              ))}
            </>
          )}
        </main>
      </div>
    </div>
  )
}

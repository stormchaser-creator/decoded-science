import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { API, s, useIsMobile } from '../shared.js'
import { TypeTag, StrengthBar, Loading, ErrorMsg } from '../components/ui.jsx'

const CONNECTION_TYPES = [
  'contradicts', 'extends', 'mechanism_for',
  'shares_target', 'methodological_parallel', 'convergent_evidence',
]

export default function ConnectionsPage() {
  const isMobile = useIsMobile()
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
    <div style={isMobile ? { display: 'flex', flexDirection: 'column' } : s.twoCol}>
      <aside style={isMobile ? { padding: '16px', borderBottom: '1px solid #1e1e2e', background: '#0d0d18' } : s.sidebar}>
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
        <div style={{ fontSize: '12px', color: '#6b7280' }}>Showing {connections.length} of {total}</div>
      </aside>
      <main style={isMobile ? { padding: '16px' } : s.content}>
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
              <p style={{ fontSize: '13px', color: '#a0a0b8', marginTop: '8px', lineHeight: '1.6' }}>{c.description}</p>
            )}
            <StrengthBar confidence={c.confidence} novelty={c.novelty_score} />
          </div>
        ))}
      </main>
    </div>
  )
}

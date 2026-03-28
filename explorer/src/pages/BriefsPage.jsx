import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { API, s } from '../shared.js'
import { Loading, ErrorMsg } from '../components/ui.jsx'

export default function BriefsPage() {
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

  const toggle = key => setExpanded(p => ({ ...p, [key]: !p[key] }))

  return (
    <div style={s.page}>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 6px' }}>Intelligence Briefs</h2>
        <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>
          AI-generated quality assessments and connection summaries for extracted papers.
          {total > 0 && ` ${total} total.`}
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

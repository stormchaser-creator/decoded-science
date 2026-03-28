import React, { useState, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { API, s, parseJsonField } from '../shared.js'
import { TypeTag, StrengthBar, Loading, ErrorMsg } from '../components/ui.jsx'

export default function PaperDetailPage() {
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

import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api.js'

function Section({ title, children }) {
  return (
    <div style={{
      background: '#12121e',
      border: '1px solid #1e1e2e',
      borderRadius: 8,
      padding: '20px',
      marginBottom: 16,
    }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 12 }}>
        {title}
      </div>
      {children}
    </div>
  )
}

function Tag({ children, color = '#9991d0', bg = '#1e1e2e' }) {
  return (
    <span style={{ display: 'inline-block', background: bg, borderRadius: 4, padding: '3px 9px', fontSize: 12, color, marginRight: 6, marginTop: 4 }}>
      {children}
    </span>
  )
}

export default function PaperDetail() {
  const { id } = useParams()
  const [paper, setPaper] = useState(null)
  const [connections, setConnections] = useState([])
  const [critique, setCritique] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    Promise.all([
      api.paper(id),
      api.paperConnections(id).catch(() => ({ connections: [] })),
      api.paperCritique(id).catch(() => null),
    ]).then(([p, c, cr]) => {
      setPaper(p)
      setConnections(c?.connections || [])
      setCritique(cr)
      setLoading(false)
    }).catch(e => {
      setError('Failed to load paper.')
      setLoading(false)
    })
  }, [id])

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '80px 0', color: '#6b7280', fontSize: 14 }}>Loading paper…</div>
  }

  if (error || !paper) {
    return (
      <div style={{ textAlign: 'center', padding: '80px 0' }}>
        <div style={{ color: '#f87171', fontSize: 14, marginBottom: 16 }}>{error || 'Paper not found.'}</div>
        <Link to="/papers" style={{ color: '#7c6af7', fontSize: 14 }}>← Back to papers</Link>
      </div>
    )
  }

  const year = paper.published_date ? String(paper.published_date).slice(0, 4) : null
  const extraction = paper.extraction_results || {}
  const entities = extraction.entities || []
  const claims = extraction.claims || []

  return (
    <div className="max-w-3xl">
      <Link to="/papers" style={{ display: 'inline-block', marginBottom: 20, fontSize: 13, color: '#7c6af7' }}>
        ← All Papers
      </Link>

      {/* Main metadata */}
      <Section title="Paper">
        <h1 style={{ fontSize: 20, fontWeight: 700, color: '#e0e0e8', lineHeight: 1.4, margin: '0 0 12px' }}>
          {paper.title}
        </h1>
        <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 12, lineHeight: 1.7 }}>
          {paper.authors && <div><span style={{ color: '#9ca3af' }}>Authors: </span>{paper.authors}</div>}
          {paper.journal && <div><span style={{ color: '#9ca3af' }}>Journal: </span>{paper.journal}</div>}
          {year && <div><span style={{ color: '#9ca3af' }}>Year: </span>{year}</div>}
          {paper.doi && (
            <div>
              <span style={{ color: '#9ca3af' }}>DOI: </span>
              <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noopener noreferrer" style={{ color: '#7c6af7' }}>
                {paper.doi}
              </a>
            </div>
          )}
        </div>
        <div>
          {paper.status && <Tag bg="rgba(74,222,128,0.08)" color="#4ade80">{paper.status}</Tag>}
          {paper.study_design && <Tag>{paper.study_design}</Tag>}
          {paper.sample_size && <Tag>n={paper.sample_size}</Tag>}
          {paper.source && <Tag>{paper.source}</Tag>}
        </div>
      </Section>

      {/* Abstract */}
      {paper.abstract && (
        <Section title="Abstract">
          <p style={{ fontSize: 14, color: '#a0a0b8', lineHeight: 1.7, margin: 0 }}>
            {paper.abstract}
          </p>
        </Section>
      )}

      {/* Extracted entities */}
      {entities.length > 0 && (
        <Section title={`Extracted Entities (${entities.length})`}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {entities.map((e, i) => (
              <span key={i} style={{ background: '#12121e', border: '1px solid #2a2a3e', borderRadius: 4, padding: '4px 10px', fontSize: 12, color: '#9991d0' }}>
                {typeof e === 'string' ? e : e.name || e.text || JSON.stringify(e)}
              </span>
            ))}
          </div>
        </Section>
      )}

      {/* Extracted claims */}
      {claims.length > 0 && (
        <Section title={`Extracted Claims (${claims.length})`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {claims.slice(0, 10).map((c, i) => (
              <div key={i} style={{ fontSize: 13, color: '#a0a0b8', lineHeight: 1.5, paddingLeft: 12, borderLeft: '2px solid #2a2a3e' }}>
                {typeof c === 'string' ? c : c.text || c.claim || JSON.stringify(c)}
              </div>
            ))}
            {claims.length > 10 && <div style={{ fontSize: 12, color: '#6b7280' }}>+{claims.length - 10} more claims</div>}
          </div>
        </Section>
      )}

      {/* Connections */}
      {connections.length > 0 && (
        <Section title={`Connections (${connections.length})`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {connections.map((c, i) => (
              <div key={i} style={{ padding: '10px 0', borderBottom: i < connections.length - 1 ? '1px solid #1e1e2e' : 'none', fontSize: 13 }}>
                <span style={{ color: '#9991d0' }}>{c.entity_a || c.source_concept}</span>
                <span style={{ color: '#6b7280', margin: '0 8px' }}>
                  → {c.connection_type || c.relationship_type || 'relates to'} →
                </span>
                <span style={{ color: '#9991d0' }}>{c.entity_b || c.target_concept}</span>
                {(c.confidence != null) && (
                  <span style={{ marginLeft: 10, background: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.2)', borderRadius: 4, padding: '1px 6px', fontSize: 11, color: '#4ade80' }}>
                    {(c.confidence * 100).toFixed(0)}%
                  </span>
                )}
                {c.description && (
                  <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4, lineHeight: 1.5 }}>{c.description}</div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Intelligence Brief */}
      {critique && (
        <Section title="Intelligence Brief">
          {critique.brief && (
            <div style={{ fontSize: 14, color: '#a0a0b8', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
              {typeof critique.brief === 'string' ? critique.brief : JSON.stringify(critique.brief, null, 2)}
            </div>
          )}
          {critique.key_findings && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6, fontWeight: 600 }}>Key Findings</div>
              {Array.isArray(critique.key_findings) ? (
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {critique.key_findings.map((f, i) => (
                    <li key={i} style={{ fontSize: 13, color: '#a0a0b8', lineHeight: 1.6, marginBottom: 4 }}>{f}</li>
                  ))}
                </ul>
              ) : (
                <div style={{ fontSize: 13, color: '#a0a0b8', lineHeight: 1.6 }}>{critique.key_findings}</div>
              )}
            </div>
          )}
          {!critique.brief && !critique.key_findings && (
            <pre style={{ fontSize: 12, color: '#8b8ba8', lineHeight: 1.5, overflowX: 'auto', whiteSpace: 'pre-wrap', margin: 0 }}>
              {JSON.stringify(critique, null, 2)}
            </pre>
          )}
        </Section>
      )}
    </div>
  )
}

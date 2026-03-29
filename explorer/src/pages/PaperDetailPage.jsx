import React, { useState, useEffect, Suspense } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { API, s, parseJsonField, connectionEpistemicColor, EPISTEMIC, useIsMobile } from '../shared.js'
import { TypeTag, StrengthBar, Loading, ErrorMsg } from '../components/ui.jsx'

const ForceGraph2D = React.lazy(() => import('react-force-graph-2d'))

const DISCIPLINE_COLORS = {
  pubmed: '#7c6af7', biorxiv: '#10b981', medrxiv: '#f59e0b',
  arxiv: '#60a5fa', crossref: '#a78bfa', default: '#94a3b8',
}
const EDGE_COLORS = {
  contradicts: '#f43f5e', extends: '#10b981', mechanism_for: '#3b82f6',
  shares_target: '#c084fc', methodological_parallel: '#94a3b8',
  convergent_evidence: '#f59e0b', default: '#4b5563',
}

function MiniGraph({ paperId, connections }) {
  const navigate = useNavigate()
  const nodes = []
  const links = []
  const seen = new Set()

  // Center node
  nodes.push({ id: paperId, val: 12, center: true, source: 'center' })
  seen.add(paperId)

  connections.slice(0, 15).forEach(c => {
    const isA = String(c.paper_a_id) === String(paperId)
    const otherId = String(isA ? c.paper_b_id : c.paper_a_id)
    const otherTitle = isA ? c.paper_b_title : c.paper_a_title
    if (!seen.has(otherId)) {
      nodes.push({ id: otherId, title: otherTitle, val: 4, source: 'neighbor' })
      seen.add(otherId)
    }
    links.push({ source: paperId, target: otherId, type: c.connection_type, confidence: c.confidence })
  })

  if (nodes.length < 2) return null

  return (
    <Suspense fallback={<div style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280', fontSize: '12px' }}>Loading graph…</div>}>
      <ForceGraph2D
        graphData={{ nodes, links }}
        width={300}
        height={300}
        backgroundColor="#0a0a0f"
        nodeColor={n => n.center ? '#7c6af7' : DISCIPLINE_COLORS[n.source] || DISCIPLINE_COLORS.default}
        nodeVal={n => n.val}
        linkColor={l => EDGE_COLORS[l.type] || EDGE_COLORS.default}
        linkWidth={1}
        onNodeClick={node => { if (!node.center) navigate(`/papers/${node.id}`) }}
        nodeLabel={n => n.title || n.id}
        cooldownTicks={60}
        enableZoomInteraction={false}
        enablePanInteraction={false}
      />
    </Suspense>
  )
}

function ClaimItem({ claim }) {
  const text = typeof claim === 'string' ? claim : (claim.text || claim.claim || JSON.stringify(claim))
  const strength = typeof claim === 'object' ? claim.evidence_strength : null
  const color = connectionEpistemicColor(strength) || EPISTEMIC.speculation
  return (
    <div style={{
      padding: '8px 12px',
      borderLeft: `3px solid ${color}`,
      marginBottom: '6px',
      background: 'rgba(0,0,0,0.2)',
      borderRadius: '0 4px 4px 0',
    }}>
      <div style={{ fontSize: '13px', color: '#a0a0b8', lineHeight: '1.6' }}>{text}</div>
      {strength && (
        <div style={{ fontSize: '10px', color, marginTop: '3px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{strength}</div>
      )}
    </div>
  )
}

export default function PaperDetailPage() {
  const { id } = useParams()
  const isMobile = useIsMobile()
  const [paper, setPaper] = useState(null)
  const [connections, setConnections] = useState([])
  const [critique, setCritique] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showEntities, setShowEntities] = useState(false)
  const [showClaims, setShowClaims] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetch(`${API}/papers/${id}`).then(r => r.json()),
      fetch(`${API}/papers/${id}/connections`).then(r => r.json()),
      fetch(`${API}/papers/${id}/critique`).then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([p, c, cr]) => {
      setPaper(p)
      setConnections(c.connections || [])
      setCritique(cr)
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

  // Sort connections by novelty_score DESC
  const sortedConns = [...connections].sort((a, b) => (b.novelty_score || 0) - (a.novelty_score || 0))

  return (
    <div style={{ ...s.page, maxWidth: '1200px', padding: isMobile ? '16px' : '24px' }}>
      <Link to="/papers" style={s.btnOutline}>← Back</Link>

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '65% 35%', gap: '20px', marginTop: '16px', alignItems: 'start' }}>

        {/* LEFT COLUMN */}
        <div>
          {/* Header */}
          <div style={s.card}>
            <h1 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '8px', lineHeight: '1.4', color: '#e0e0e8' }}>
              {paper.title}
            </h1>
            <div style={s.paperMeta}>
              {paper.authors && Array.isArray(paper.authors) && paper.authors.length > 0 && (
                <span>
                  {paper.authors.slice(0, 3).map(a => typeof a === 'string' ? a : a.name || '').filter(Boolean).join(', ')}
                  {paper.authors.length > 3 && ' et al.'} · </span>
              )}
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

          {/* Entities */}
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
                    <span key={i} style={{
                      ...s.tag,
                      borderLeft: `3px solid ${EPISTEMIC.interpretation}`,
                      marginTop: 0,
                      color: '#c4bef8',
                      background: '#140a20',
                    }}>
                      {typeof e === 'string' ? e : (e.name || e.text || JSON.stringify(e))}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Claims with epistemic colors */}
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
                  {claims.map((c, i) => <ClaimItem key={i} claim={c} />)}
                </div>
              )}
            </div>
          )}

          {/* Mechanisms */}
          {mechanisms.length > 0 && (
            <div style={{ ...s.card, marginTop: '12px' }}>
              <div style={{ ...s.sectionTitle, marginBottom: '8px' }}>Mechanisms ({mechanisms.length})</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {mechanisms.map((m, i) => {
                  const desc = typeof m === 'string' ? m : (m.description || m.name || m.text || null)
                  if (!desc) return null
                  const subtext = typeof m === 'object' && m.upstream_entity && m.downstream_entity
                    ? `${m.upstream_entity} → ${m.interaction_type || 'affects'} → ${m.downstream_entity}`
                    : null
                  return (
                    <div key={i} style={{ borderLeft: `3px solid ${EPISTEMIC.hypothesis}`, paddingLeft: '10px', paddingTop: '4px', paddingBottom: '4px' }}>
                      <div style={{ fontSize: '13px', color: '#93c5fd', lineHeight: '1.6' }}>{desc}</div>
                      {subtext && <div style={{ fontSize: '11px', color: '#4b5563', marginTop: '2px', fontFamily: 'monospace' }}>{subtext}</div>}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Intelligence Brief */}
          {critique && (
            <div style={{ ...s.card, marginTop: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={s.sectionTitle}>Intelligence Brief</div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {critique.overall_quality && (
                    <span style={{
                      ...s.tag,
                      marginTop: 0,
                      ...(critique.overall_quality === 'high' ? s.tagGreen : critique.overall_quality === 'medium' ? s.tagYellow : s.tagRed),
                      fontWeight: '700',
                    }}>
                      {critique.overall_quality === 'high' ? 'HIGH' : critique.overall_quality === 'medium' ? 'MED' : 'LOW'}
                    </span>
                  )}
                </div>
              </div>
              {(critique.summary || critique.brief) && (
                <p style={{ fontSize: '13px', color: '#a0a0b8', lineHeight: '1.7', whiteSpace: 'pre-wrap', margin: 0 }}>
                  {critique.summary || critique.brief}
                </p>
              )}
            </div>
          )}
        </div>

        {/* RIGHT COLUMN (sticky on desktop) */}
        <div style={isMobile ? {} : { position: 'sticky', top: '70px' }}>
          {/* Mini graph */}
          {connections.length > 0 && (
            <div style={{ ...s.card, marginBottom: '12px', padding: '12px' }}>
              <div style={{ ...s.sectionTitle, marginBottom: '8px' }}>Neighborhood Graph</div>
              <div style={{ border: '1px solid #1e1e2e', borderRadius: '6px', overflow: 'hidden' }}>
                <MiniGraph paperId={id} connections={connections} />
              </div>
            </div>
          )}

          {/* Connections sorted by novelty */}
          {sortedConns.length > 0 && (
            <div style={s.card}>
              <div style={{ ...s.sectionTitle, marginBottom: '8px' }}>
                Connections ({sortedConns.length})
                <span style={{ fontSize: '10px', color: '#4b4b6b', marginLeft: '6px', fontWeight: '400', textTransform: 'none', letterSpacing: 0 }}>sorted by novelty</span>
              </div>
              {sortedConns.map((c, i) => {
                const isA = String(c.paper_a_id) === String(id)
                const otherId = isA ? c.paper_b_id : c.paper_a_id
                const otherTitle = isA ? c.paper_b_title : c.paper_a_title
                const borderColor = EDGE_COLORS[c.connection_type] || EDGE_COLORS.default
                return (
                  <div key={c.id || i} style={{
                    borderLeft: `3px solid ${borderColor}`,
                    paddingLeft: '10px',
                    marginBottom: '10px',
                    paddingBottom: '10px',
                    borderBottom: i < sortedConns.length - 1 ? '1px solid #1a1a2e' : 'none',
                  }}>
                    <div style={{ marginBottom: '4px' }}>
                      <TypeTag type={c.connection_type} />
                    </div>
                    <Link to={`/papers/${otherId}`} style={{ fontSize: '12px', color: '#c4bef8', lineHeight: '1.4', textDecoration: 'none' }}>
                      {(otherTitle || '').substring(0, 80)}{otherTitle?.length > 80 ? '…' : ''}
                    </Link>
                    {c.description && (
                      <p style={{ fontSize: '11px', color: '#6b7280', margin: '4px 0 0', lineHeight: '1.5' }}>
                        {c.description.substring(0, 120)}{c.description.length > 120 ? '…' : ''}
                      </p>
                    )}
                    <div style={{ display: 'flex', gap: '12px', marginTop: '4px', fontSize: '10px', color: '#4b4b6b' }}>
                      <span>Conf: {((c.confidence || 0) * 100).toFixed(0)}%</span>
                      {c.novelty_score && <span>Novelty: {((c.novelty_score || 0) * 100).toFixed(0)}%</span>}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Request Analysis button */}
          <div style={{ ...s.card, marginTop: '12px', textAlign: 'center' }}>
            <Link
              to={`/analyze?doi=${encodeURIComponent(paper.doi || '')}`}
              style={{ ...s.btn, display: 'inline-block', textDecoration: 'none', fontSize: '12px', padding: '8px 16px' }}
            >
              Request Analysis
            </Link>
            <div style={{ fontSize: '11px', color: '#4b4b6b', marginTop: '6px' }}>
              Re-run extraction & connection discovery
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

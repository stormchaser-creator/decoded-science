import React, { useState, useEffect, Suspense } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { API, s, parseJsonField, connectionEpistemicColor, EPISTEMIC, useIsMobile } from '../shared.js'
import { TypeTag, StrengthBar, Loading, ErrorMsg } from '../components/ui.jsx'
import { useAuth } from '../auth.jsx'
import SEO from '../components/SEO.jsx'
import ChatPanel from '../components/ChatPanel.jsx'

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

function ConnGroup({ type, items, paperId, isMobile }) {
  const [expanded, setExpanded] = React.useState(items.length <= 5)
  const borderColor = EDGE_COLORS[type] || EDGE_COLORS.default
  const shown = expanded ? items : items.slice(0, 5)
  return (
    <div id={`conn-group-${type}`} style={{ ...{ background: '#12121e', borderRadius: '8px', padding: '16px' }, marginBottom: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
        <div style={{ width: '4px', height: '20px', background: borderColor, borderRadius: '2px' }} />
        <span style={{ fontSize: '13px', fontWeight: '700', color: borderColor, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          {type.replace(/_/g, ' ')}
        </span>
        <span style={{ fontSize: '11px', color: '#4b4b6b' }}>({items.length})</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: '10px' }}>
        {shown.map((c, i) => {
          const isA = String(c.paper_a_id) === String(paperId)
          const otherId = isA ? c.paper_b_id : c.paper_a_id
          const otherTitle = isA ? c.paper_b_title : c.paper_a_title
          return (
            <div key={c.id || i} style={{
              background: '#0e0e1a', borderRadius: '8px', padding: '12px',
              borderLeft: `3px solid ${borderColor}`,
            }}>
              <Link to={`/papers/${otherId}`} style={{ fontSize: '12px', color: '#c4bef8', lineHeight: '1.5', textDecoration: 'none', fontWeight: '500', display: 'block', marginBottom: '6px' }}>
                {otherTitle || 'Untitled'}
              </Link>
              {c.description && (
                <p style={{ fontSize: '11px', color: '#7a74a8', margin: 0, lineHeight: '1.6' }}>
                  {c.description}
                </p>
              )}
              <div style={{ display: 'flex', gap: '10px', marginTop: '6px', fontSize: '10px', color: '#4b4b6b' }}>
                <span>Conf: {((c.confidence || 0) * 100).toFixed(0)}%</span>
                {c.novelty_score != null && <span>Novelty: {((c.novelty_score || 0) * 100).toFixed(0)}%</span>}
              </div>
            </div>
          )
        })}
      </div>
      {items.length > 5 && (
        <button onClick={() => setExpanded(!expanded)} style={{
          background: 'transparent', border: '1px solid #2d2060', color: '#7c6af7',
          borderRadius: '6px', padding: '6px 14px', fontSize: '11px', cursor: 'pointer',
          marginTop: '10px', width: '100%',
        }}>
          {expanded ? `Show fewer` : `Show all ${items.length} ${type.replace(/_/g, ' ')} connections`}
        </button>
      )}
    </div>
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
  const { user, token } = useAuth()
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
      <SEO
        title={`AI Analysis: ${paper.title}`}
        description={paper.abstract ? paper.abstract.substring(0, 155) + '…' : `Deep AI analysis of "${paper.title}" including extracted entities, methodological critique, missed connections, and convergence cluster mapping.`}
        path={`/papers/${paper.id}`}
        type="article"
        schema={{
          "@context": "https://schema.org",
          "@type": "ScholarlyArticle",
          "name": paper.title,
          "description": paper.abstract || '',
          "url": `https://thedecodedhuman.com/papers/${paper.id}`,
          "datePublished": paper.published_date || undefined,
          "author": Array.isArray(paper.authors) ? paper.authors.map(a => typeof a === 'string' ? a : a.name).filter(Boolean).join(', ') : undefined,
          "isPartOf": {
            "@type": "WebApplication",
            "name": "The Decoded Human",
            "url": "https://thedecodedhuman.com"
          }
        }}
      />
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
            <div style={{ marginTop: '8px', display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
              <span style={{ ...s.tag, ...(paper.status === 'extracted' || paper.status === 'connected' ? s.tagGreen : {}) }}>
                {paper.status}
              </span>
              {paper.data_source && (
                <span style={{
                  ...s.tag,
                  ...(paper.data_source?.startsWith('full_text') ? s.tagGreen : { background: '#1a1500', color: '#fbbf24' }),
                }}>
                  {paper.data_source?.startsWith('full_text') ? 'Full Text' : 'Abstract Only'}
                </span>
              )}
              {paper.study_design && <span style={s.tag}>{paper.study_design}</span>}
              {paper.sample_size && <span style={s.tag}>n={paper.sample_size}</span>}
            </div>
            {paper.abstract && (() => {
              // Try to parse structured abstract sections
              const sectionLabels = ['Background', 'Introduction', 'Objective', 'Objectives', 'Aim', 'Aims',
                'Purpose', 'Methods', 'Materials and Methods', 'Study Design', 'Design',
                'Results', 'Findings', 'Outcomes', 'Conclusion', 'Conclusions', 'Discussion',
                'Significance', 'Interpretation', 'Context', 'Setting', 'Participants',
                'Interventions', 'Main Outcome Measures', 'Measurements']
              const pattern = new RegExp(`(?:^|\\n|\\. )(?=(?:${sectionLabels.join('|')})\\s*:)`, 'gi')
              const raw = paper.abstract.trim()
              // Check if abstract has section markers
              const hasStructure = sectionLabels.some(l => {
                const re = new RegExp(`(?:^|\\n|\\. )${l}\\s*:`, 'i')
                return re.test(raw)
              })
              if (!hasStructure) {
                // Break long unstructured abstracts into readable paragraphs
                // Split on sentences and group ~3 per paragraph
                const sentences = raw.split(/(?<=\.)\s+(?=[A-Z])/)
                if (sentences.length <= 3) {
                  return <p style={{ fontSize: '13px', color: '#a0a0b8', marginTop: '16px', lineHeight: '1.8' }}>{raw}</p>
                }
                const paragraphs = []
                for (let si = 0; si < sentences.length; si += 3) {
                  paragraphs.push(sentences.slice(si, si + 3).join(' '))
                }
                return (
                  <div style={{ marginTop: '16px' }}>
                    {paragraphs.map((p, i) => (
                      <p key={i} style={{ fontSize: '13px', color: '#a0a0b8', lineHeight: '1.8', margin: '0 0 12px' }}>{p}</p>
                    ))}
                  </div>
                )
              }
              // Parse into sections
              const sections = []
              const splitRe = new RegExp(`((?:${sectionLabels.join('|')})\\s*):`, 'gi')
              let lastIndex = 0
              let lastLabel = null
              let match
              // Collect preamble if any
              const firstMatch = splitRe.exec(raw)
              if (firstMatch && firstMatch.index > 0) {
                const preamble = raw.substring(0, firstMatch.index).trim()
                if (preamble) sections.push({ label: null, text: preamble })
              }
              if (firstMatch) {
                lastLabel = firstMatch[1].trim()
                lastIndex = firstMatch.index + firstMatch[0].length
              }
              splitRe.lastIndex = firstMatch ? firstMatch.index + firstMatch[0].length : 0
              while ((match = splitRe.exec(raw)) !== null) {
                if (lastLabel) {
                  sections.push({ label: lastLabel, text: raw.substring(lastIndex, match.index).trim().replace(/\.\s*$/, '.') })
                }
                lastLabel = match[1].trim()
                lastIndex = match.index + match[0].length
              }
              if (lastLabel) {
                sections.push({ label: lastLabel, text: raw.substring(lastIndex).trim() })
              }
              if (sections.length === 0) {
                return <p style={{ fontSize: '13px', color: '#a0a0b8', marginTop: '16px', lineHeight: '1.8' }}>{raw}</p>
              }
              const sectionColors = {
                background: '#60a5fa', introduction: '#60a5fa', context: '#60a5fa',
                objective: '#c084fc', objectives: '#c084fc', aim: '#c084fc', aims: '#c084fc', purpose: '#c084fc',
                methods: '#fbbf24', 'materials and methods': '#fbbf24', 'study design': '#fbbf24', design: '#fbbf24',
                setting: '#fbbf24', participants: '#fbbf24', interventions: '#fbbf24', 'main outcome measures': '#fbbf24',
                measurements: '#fbbf24',
                results: '#4ade80', findings: '#4ade80', outcomes: '#4ade80',
                conclusion: '#f87171', conclusions: '#f87171', discussion: '#f87171',
                significance: '#f87171', interpretation: '#f87171',
              }
              return (
                <div style={{ marginTop: '16px' }}>
                  {sections.map((sec, i) => (
                    <div key={i} style={{ marginBottom: '14px' }}>
                      {sec.label && (
                        <div style={{
                          fontSize: '11px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.5px',
                          color: sectionColors[sec.label.toLowerCase()] || '#7c6af7', marginBottom: '4px',
                        }}>
                          {sec.label}
                        </div>
                      )}
                      <p style={{
                        fontSize: '13px', color: '#a0a0b8', lineHeight: '1.8', margin: 0,
                        paddingLeft: sec.label ? '12px' : '0',
                        borderLeft: sec.label ? `2px solid ${sectionColors[sec.label.toLowerCase()] || '#2d2060'}33` : 'none',
                      }}>
                        {sec.text}
                      </p>
                    </div>
                  ))}
                </div>
              )
            })()}
            {paper.key_findings && (() => {
              let findings = paper.key_findings
              if (typeof findings === 'string') {
                try { findings = JSON.parse(findings) } catch { findings = [findings] }
              }
              if (!Array.isArray(findings)) findings = [findings]
              findings = findings.filter(f => f && typeof f === 'string' && f.length > 10)
              if (findings.length === 0) return null
              return (
                <div style={{ marginTop: '16px' }}>
                  <div style={{ fontSize: '11px', color: '#6b7280', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '10px' }}>Key Findings</div>
                  {findings.map((f, i) => (
                    <div key={i} style={{ fontSize: '13px', color: '#a0a0b8', lineHeight: '1.7', marginBottom: '8px', paddingLeft: '14px', borderLeft: '2px solid #2d2060' }}>
                      {typeof f === 'string' ? f : JSON.stringify(f)}
                    </div>
                  ))}
                </div>
              )
            })()}
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
                  {entities.map((e, i) => {
                    const name = typeof e === 'string' ? e : (e.name || e.text || JSON.stringify(e))
                    const conf = typeof e === 'object' ? e.confidence : null
                    // Use just the short name for search (strip parenthetical like "GDF11 (Growth...)")
                    const searchName = name.replace(/\s*\(.*?\)\s*$/, '').trim()
                    return (
                      <Link key={i} to={`/papers?q=${encodeURIComponent(searchName)}`} style={{
                        ...s.tag,
                        borderLeft: `3px solid ${EPISTEMIC.interpretation}`,
                        marginTop: 0,
                        color: '#c4bef8',
                        background: '#140a20',
                        textDecoration: 'none',
                        cursor: 'pointer',
                        transition: 'background 0.15s',
                      }}
                        onMouseEnter={ev => ev.currentTarget.style.background = '#1e1035'}
                        onMouseLeave={ev => ev.currentTarget.style.background = '#140a20'}
                      >
                        {name}{conf != null && <span style={{ color: '#4b4b6b', marginLeft: '4px', fontSize: '9px' }}>{Math.round(conf * 100)}%</span>}
                      </Link>
                    )
                  })}
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
          {critique && critique.brief_confidence === 'insufficient' && (
            <div style={{ ...s.card, marginTop: '12px', padding: '20px' }}>
              <div style={s.sectionTitle}>Intelligence Brief</div>
              <div style={{ background: '#1a1500', border: '1px solid #3d2e00', borderRadius: '8px', padding: '16px', marginTop: '12px', textAlign: 'center' }}>
                <div style={{ fontSize: '24px', marginBottom: '8px' }}>&#9888;</div>
                <div style={{ fontSize: '13px', color: '#fbbf24', fontWeight: '600', marginBottom: '6px' }}>Insufficient Data for Analysis</div>
                <div style={{ fontSize: '12px', color: '#9991d0', lineHeight: '1.6' }}>
                  This paper {paper.data_source === 'abstract_only' ? 'only has an abstract available — no full text was found' : 'has limited extracted data'}.
                  The system requires enough entities and claims to generate a reliable intelligence brief.
                  {paper.source === 'medrxiv' || paper.source === 'biorxiv' ? ' Full text may become available as preprint servers update.' : ''}
                </div>
              </div>
            </div>
          )}
          {critique && critique.brief_confidence !== 'insufficient' && (
            <div style={{ ...s.card, marginTop: '12px', padding: '20px' }}>
              {/* Data quality warning */}
              {(critique.brief_confidence === 'low' || (!critique.brief_confidence && paper.data_source === 'abstract_only')) && (
                <div style={{ background: '#1a1500', border: '1px solid #3d2e00', borderRadius: '6px', padding: '10px 14px', marginBottom: '14px', fontSize: '12px', color: '#fbbf24', lineHeight: '1.6' }}>
                  This analysis was generated from {paper.data_source === 'abstract_only' ? 'the abstract only — full paper text was not available' : 'limited data'}. Scores and assessments may not reflect the full paper.
                </div>
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div style={s.sectionTitle}>Intelligence Brief</div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  {critique.recommendation && (
                    <span style={{ ...s.tag, marginTop: 0, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.5px', ...s.tagBlue }}>
                      {critique.recommendation}
                    </span>
                  )}
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

              {/* Score bars */}
              {(critique.methodology_score || critique.reproducibility_score || critique.novelty_score || critique.statistical_rigor) && (
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : '1fr 1fr 1fr 1fr', gap: '10px', marginBottom: '16px' }}>
                  {[
                    { label: 'Methodology', score: critique.methodology_score, color: '#7c6af7' },
                    { label: 'Reproducibility', score: critique.reproducibility_score, color: '#4ade80' },
                    { label: 'Novelty', score: critique.novelty_score, color: '#fbbf24' },
                    { label: 'Statistical Rigor', score: critique.statistical_rigor, color: '#60a5fa' },
                  ].filter(s => s.score != null).map(({ label, score, color }) => (
                    <div key={label} style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '20px', fontWeight: '700', color }}>{typeof score === 'number' ? score.toFixed(1) : score}</div>
                      <div style={{ fontSize: '10px', color: '#6b7280', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{label}</div>
                      <div style={{ marginTop: '4px', height: '3px', background: '#1e1e2e', borderRadius: '2px', overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${(parseFloat(score) || 0) * 10}%`, background: color, borderRadius: '2px' }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Summary */}
              {(critique.summary || critique.brief) && (
                <p style={{ fontSize: '13px', color: '#c4bef8', lineHeight: '1.8', margin: '0 0 16px', borderLeft: '3px solid #2d2060', paddingLeft: '12px' }}>
                  {critique.summary || critique.brief}
                </p>
              )}

              {/* Strengths */}
              {critique.strengths && critique.strengths.length > 0 && (
                <div style={{ marginBottom: '14px' }}>
                  <div style={{ fontSize: '11px', fontWeight: '700', color: '#4ade80', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px' }}>Strengths</div>
                  {(typeof critique.strengths === 'string' ? [critique.strengths] : critique.strengths).map((s, i) => (
                    <div key={i} style={{ fontSize: '12px', color: '#9991d0', lineHeight: '1.7', marginBottom: '6px', paddingLeft: '12px', borderLeft: '2px solid #0d2010' }}>
                      {typeof s === 'string' ? s : s.text || JSON.stringify(s)}
                    </div>
                  ))}
                </div>
              )}

              {/* Weaknesses */}
              {critique.weaknesses && critique.weaknesses.length > 0 && (
                <div style={{ marginBottom: '14px' }}>
                  <div style={{ fontSize: '11px', fontWeight: '700', color: '#fbbf24', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px' }}>Weaknesses</div>
                  {(typeof critique.weaknesses === 'string' ? [critique.weaknesses] : critique.weaknesses).map((w, i) => (
                    <div key={i} style={{ fontSize: '12px', color: '#9991d0', lineHeight: '1.7', marginBottom: '6px', paddingLeft: '12px', borderLeft: '2px solid #1a1500' }}>
                      {typeof w === 'string' ? w : w.text || JSON.stringify(w)}
                    </div>
                  ))}
                </div>
              )}

              {/* Red Flags */}
              {critique.red_flags && critique.red_flags.length > 0 && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: '700', color: '#f87171', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px' }}>Red Flags</div>
                  {(typeof critique.red_flags === 'string' ? [critique.red_flags] : critique.red_flags).map((r, i) => (
                    <div key={i} style={{ fontSize: '12px', color: '#9991d0', lineHeight: '1.7', marginBottom: '6px', paddingLeft: '12px', borderLeft: '2px solid #1a0808' }}>
                      {typeof r === 'string' ? r : r.text || JSON.stringify(r)}
                    </div>
                  ))}
                </div>
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

          {/* Connection type summary */}
          {sortedConns.length > 0 && (() => {
            const groups = {}
            sortedConns.forEach(c => {
              const t = c.connection_type || 'other'
              if (!groups[t]) groups[t] = []
              groups[t].push(c)
            })
            return (
              <div style={s.card}>
                <div style={{ ...s.sectionTitle, marginBottom: '12px' }}>
                  Connections ({sortedConns.length})
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {Object.entries(groups).sort((a, b) => {
                    const order = ['contradicts', 'extends', 'mechanism_for', 'convergent_evidence', 'shares_target', 'methodological_parallel']
                    return (order.indexOf(a[0]) === -1 ? 99 : order.indexOf(a[0])) - (order.indexOf(b[0]) === -1 ? 99 : order.indexOf(b[0]))
                  }).map(([type, items]) => (
                    <button key={type} onClick={() => {
                      const el = document.getElementById(`conn-group-${type}`)
                      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
                    }} style={{
                      background: 'transparent', border: `1px solid ${EDGE_COLORS[type] || EDGE_COLORS.default}`,
                      color: EDGE_COLORS[type] || EDGE_COLORS.default, borderRadius: '12px',
                      padding: '4px 10px', fontSize: '11px', cursor: 'pointer', fontWeight: '600',
                    }}>
                      {type.replace(/_/g, ' ')} ({items.length})
                    </button>
                  ))}
                </div>
              </div>
            )
          })()}

          {/* AI Chat — admin only */}
          {user?.role === 'admin' && token && (
            <div style={{ marginTop: '12px' }}>
              <ChatPanel paperId={id} token={token} connections={connections} />
            </div>
          )}
        </div>
      </div>

      {/* CONNECTIONS — full width below the 2-column layout, grouped by type */}
      {sortedConns.length > 0 && (() => {
        const groups = {}
        sortedConns.forEach(c => {
          const t = c.connection_type || 'other'
          if (!groups[t]) groups[t] = []
          groups[t].push(c)
        })
        const typeOrder = ['contradicts', 'extends', 'mechanism_for', 'convergent_evidence', 'shares_target', 'methodological_parallel']
        const sortedGroups = Object.entries(groups).sort((a, b) => {
          return (typeOrder.indexOf(a[0]) === -1 ? 99 : typeOrder.indexOf(a[0])) - (typeOrder.indexOf(b[0]) === -1 ? 99 : typeOrder.indexOf(b[0]))
        })
        return (
          <div style={{ marginTop: '20px' }}>
            <h2 style={{ fontSize: '16px', fontWeight: '700', color: '#e0e0e8', marginBottom: '16px' }}>
              Connections ({sortedConns.length})
            </h2>
            {sortedGroups.map(([type, items]) => (
              <ConnGroup key={type} type={type} items={items} paperId={id} isMobile={isMobile} />
            ))}
          </div>
        )
      })()}
    </div>
  )
}

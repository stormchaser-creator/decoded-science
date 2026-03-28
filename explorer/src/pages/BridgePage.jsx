import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { API, s, EPISTEMIC } from '../shared.js'
import { ErrorMsg } from '../components/ui.jsx'

const TIER_LABELS = {
  graph: { label: 'Graph Path', color: EPISTEMIC.convergence, icon: '🔗' },
  semantic: { label: 'Semantic Bridge', color: EPISTEMIC.interpretation, icon: '🧠' },
  llm: { label: 'LLM Hypothesis', color: EPISTEMIC.hypothesis, icon: '💡' },
}

function ConfidenceBadge({ confidence }) {
  if (!confidence) return null
  const pct = Math.round(confidence * 100)
  const color = pct >= 70 ? EPISTEMIC.convergence : pct >= 40 ? EPISTEMIC.hypothesis : EPISTEMIC.speculation
  return (
    <span style={{ fontSize: '11px', color, fontWeight: '600', background: 'rgba(0,0,0,0.2)', padding: '2px 8px', borderRadius: '4px' }}>
      {pct}% confidence
    </span>
  )
}

export default function BridgePage() {
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

  // Determine which tier we got
  const tier = result
    ? result.graph_paths_found > 0
      ? 'graph'
      : result.similar_papers?.length > 0
        ? 'semantic'
        : 'llm'
    : null

  return (
    <div style={s.page}>
      <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 6px' }}>Bridge Query</h2>
      <p style={{ fontSize: '13px', color: '#6b7280', marginBottom: '8px' }}>
        Find hidden connections between two research concepts. Three-tier search: direct graph path → semantic bridge → LLM hypothesis.
      </p>

      {/* Tier explanation */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', flexWrap: 'wrap' }}>
        {Object.entries(TIER_LABELS).map(([key, { label, color, icon }]) => (
          <div key={key} style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            padding: '4px 10px',
            background: '#12121e',
            border: `1px solid ${tier === key ? color : '#1e1e2e'}`,
            borderRadius: '16px',
            fontSize: '11px',
            color: tier === key ? color : '#6b7280',
            transition: 'border-color 0.2s',
          }}>
            <span>{icon}</span>
            <span>{label}</span>
          </div>
        ))}
      </div>

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
          <div style={{ fontSize: '24px', marginBottom: '12px' }}>⬡</div>
          <div>Running graph traversal and semantic search…</div>
          <div style={{ fontSize: '12px', marginTop: '6px', color: '#4b4b6b' }}>
            Tier 1: Direct graph path → Tier 2: Semantic bridge → Tier 3: LLM hypothesis
          </div>
        </div>
      )}
      {result && (
        <div>
          {/* Result header */}
          <div style={{ ...s.card, borderColor: '#2a2040', borderLeft: `4px solid ${TIER_LABELS[tier]?.color || '#7c6af7'}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
              <div style={{ fontWeight: '600', color: '#9991d0', fontSize: '15px' }}>
                {result.concept_a} ↔ {result.concept_b}
              </div>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                {tier && (
                  <span style={{ fontSize: '11px', color: TIER_LABELS[tier].color, fontWeight: '600', background: 'rgba(0,0,0,0.2)', padding: '2px 8px', borderRadius: '4px' }}>
                    {TIER_LABELS[tier].icon} {TIER_LABELS[tier].label}
                  </span>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '16px', marginBottom: '12px', fontSize: '12px', color: '#6b7280', flexWrap: 'wrap' }}>
              <span>🔗 {result.graph_paths_found} graph paths</span>
              <span>📄 {result.papers_a_count} papers on "{result.concept_a}"</span>
              <span>📄 {result.papers_b_count} papers on "{result.concept_b}"</span>
              {result.similar_papers?.length > 0 && <span>🔍 {result.similar_papers.length} semantic bridges</span>}
            </div>

            {result.hypothesis ? (
              <>
                <div style={{ fontSize: '11px', color: '#6b7280', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: '600' }}>
                  Bridge Hypothesis
                </div>
                <p style={{ fontSize: '14px', color: '#e0e0e8', lineHeight: '1.8', margin: 0 }}>{result.hypothesis}</p>
                {result.cost_usd > 0 && (
                  <div style={{ fontSize: '11px', color: '#4b4b6b', marginTop: '10px' }}>API cost: ${result.cost_usd.toFixed(4)}</div>
                )}
              </>
            ) : tier === 'semantic' ? (
              <div style={{ padding: '12px', background: '#0a0a1a', borderRadius: '6px', borderLeft: `3px solid ${EPISTEMIC.interpretation}` }}>
                <div style={{ fontSize: '11px', color: EPISTEMIC.interpretation, fontWeight: '600', marginBottom: '6px' }}>SEMANTIC BRIDGE</div>
                <p style={{ fontSize: '13px', color: '#a0a0b8', margin: 0, lineHeight: '1.6' }}>
                  No direct graph path found. Showing papers near both concepts via semantic similarity.
                  The intermediary papers below may contain the conceptual bridge.
                </p>
              </div>
            ) : (
              <div style={{ fontSize: '13px', color: '#6b7280' }}>
                No bridge found in the graph. Try broader concept terms or check the semantic bridges below.
              </div>
            )}
          </div>

          {/* Graph paths */}
          {result.graph_paths?.length > 0 && (
            <div style={{ marginTop: '16px' }}>
              <div style={s.sectionTitle}>Graph Paths ({result.graph_paths.length})</div>
              {result.graph_paths.map((path, i) => (
                <div key={i} style={{ ...s.card, borderLeft: `3px solid ${EPISTEMIC.convergence}` }}>
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
                          marginTop: 0,
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

          {/* Semantic bridge — intermediary papers */}
          {result.similar_papers?.length > 0 && (
            <div style={{ marginTop: '16px' }}>
              <div style={s.sectionTitle}>
                {tier === 'semantic' ? 'Semantic Bridge — Intermediary Papers' : 'Related Papers'}
              </div>
              {tier === 'semantic' && (
                <p style={{ fontSize: '12px', color: '#6b7280', marginBottom: '12px', lineHeight: '1.5' }}>
                  These papers appear near both "{result.concept_a}" and "{result.concept_b}" in embedding space.
                  They may contain the conceptual link between these domains.
                </p>
              )}
              {result.similar_papers.map((p, i) => (
                <div key={i} style={{ ...s.card, borderLeft: `3px solid ${EPISTEMIC.interpretation}` }}>
                  <Link to={`/papers/${p.paper_b_id || p.id}`} style={s.paperLink}>
                    {p.paper_b_title || p.title || 'Unknown paper'}
                  </Link>
                  {p.similarity != null && (
                    <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                      Semantic similarity: {(p.similarity * 100).toFixed(0)}%
                    </div>
                  )}
                  {p.description && (
                    <p style={{ fontSize: '12px', color: '#6b7280', margin: '6px 0 0', lineHeight: '1.5' }}>{p.description}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Papers near concept A */}
          {result.papers_a?.length > 0 && (
            <div style={{ marginTop: '16px' }}>
              <div style={s.sectionTitle}>Papers on "{result.concept_a}"</div>
              {result.papers_a.map((p, i) => (
                <div key={i} style={s.card}>
                  <Link to={`/papers/${p.id}`} style={s.paperLink}>{p.title || 'Unknown'}</Link>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

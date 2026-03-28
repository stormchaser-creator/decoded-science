import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { API, s } from '../shared.js'
import { ErrorMsg } from '../components/ui.jsx'

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
              <p style={{ fontSize: '14px', color: '#e0e0e8', lineHeight: '1.8', margin: 0 }}>{result.hypothesis}</p>
            ) : (
              <div style={{ fontSize: '13px', color: '#6b7280' }}>No bridge hypothesis generated. Try broader concept terms.</div>
            )}
            {result.cost_usd > 0 && (
              <div style={{ fontSize: '11px', color: '#4b4b6b', marginTop: '10px' }}>API cost: ${result.cost_usd.toFixed(4)}</div>
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

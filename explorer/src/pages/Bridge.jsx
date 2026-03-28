import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'

const EXAMPLES = [
  ['IL-6', 'sleep quality'],
  ['gut microbiome', 'depression'],
  ['neuroinflammation', 'cognitive decline'],
  ['mitochondria', 'aging'],
]

export default function Bridge() {
  const [conceptA, setConceptA] = useState('')
  const [conceptB, setConceptB] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!conceptA.trim() || !conceptB.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await api.bridge(conceptA.trim(), conceptB.trim())
      setResult(data)
    } catch (err) {
      setError('Bridge query failed. The API may be busy — try again.')
    }
    setLoading(false)
  }

  function useExample(a, b) {
    setConceptA(a)
    setConceptB(b)
    setResult(null)
    setError(null)
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-8">
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: '0 0 8px', color: '#e0e0e8' }}>Bridge Query</h1>
        <p style={{ fontSize: 14, color: '#6b7280', margin: 0, lineHeight: 1.6 }}>
          Discover hidden connections between two concepts across the entire paper corpus.
          The AI will find bridging paths and generate a research hypothesis.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <div style={{
          background: '#12121e',
          border: '1px solid #1e1e2e',
          borderRadius: 10,
          padding: '20px',
          marginBottom: 16,
        }}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.6px' }}>
                Concept A
              </label>
              <input
                value={conceptA}
                onChange={e => setConceptA(e.target.value)}
                placeholder="e.g. IL-6"
                style={{
                  width: '100%',
                  background: '#0a0a0f',
                  border: '1px solid #2a2a3e',
                  borderRadius: 8,
                  padding: '12px 14px',
                  fontSize: 15,
                  color: '#e0e0e8',
                  outline: 'none',
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.6px' }}>
                Concept B
              </label>
              <input
                value={conceptB}
                onChange={e => setConceptB(e.target.value)}
                placeholder="e.g. sleep quality"
                style={{
                  width: '100%',
                  background: '#0a0a0f',
                  border: '1px solid #2a2a3e',
                  borderRadius: 8,
                  padding: '12px 14px',
                  fontSize: 15,
                  color: '#e0e0e8',
                  outline: 'none',
                }}
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={loading || !conceptA.trim() || !conceptB.trim()}
            style={{
              width: '100%',
              background: loading ? '#3d3580' : '#7c6af7',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              padding: '13px',
              fontSize: 15,
              fontWeight: 600,
              cursor: loading ? 'wait' : 'pointer',
              opacity: (!conceptA.trim() || !conceptB.trim()) ? 0.5 : 1,
              transition: 'all 0.15s',
            }}
          >
            {loading ? 'Searching for bridges…' : 'Find Connections ⬡'}
          </button>
        </div>
      </form>

      {/* Examples */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 8 }}>
          Examples
        </div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map(([a, b]) => (
            <button
              key={`${a}-${b}`}
              onClick={() => useExample(a, b)}
              style={{
                background: '#12121e',
                border: '1px solid #1e1e2e',
                borderRadius: 6,
                padding: '6px 12px',
                fontSize: 12,
                color: '#9991d0',
                cursor: 'pointer',
              }}
            >
              {a} ↔ {b}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div style={{ background: '#1a0808', border: '1px solid #4a1010', borderRadius: 8, padding: '14px 16px', color: '#f87171', fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {result && (
        <div>
          {/* Header */}
          <div style={{ background: '#0d1020', border: '1px solid #2a2a4a', borderRadius: 10, padding: '20px', marginBottom: 12 }}>
            <div style={{ fontSize: 13, color: '#9991d0', marginBottom: 8, fontWeight: 600 }}>
              Bridge: {result.concept_a} ↔ {result.concept_b}
            </div>
            <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#6b7280' }}>
              <span><b style={{ color: '#7c6af7' }}>{result.graph_paths_found ?? 0}</b> graph paths</span>
              <span><b style={{ color: '#4ade80' }}>{result.similar_papers?.length ?? 0}</b> similar papers</span>
              {result.confidence != null && (
                <span><b style={{ color: '#fbbf24' }}>{(result.confidence * 100).toFixed(0)}%</b> confidence</span>
              )}
            </div>
          </div>

          {/* Hypothesis */}
          {result.hypothesis && (
            <div style={{ background: '#12121e', border: '1px solid #1e1e2e', borderRadius: 8, padding: '20px', marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 10 }}>
                Research Hypothesis
              </div>
              <p style={{ fontSize: 14, color: '#e0e0e8', lineHeight: 1.7, margin: 0 }}>
                {result.hypothesis}
              </p>
            </div>
          )}

          {/* Bridge path */}
          {result.bridge_path && result.bridge_path.length > 0 && (
            <div style={{ background: '#12121e', border: '1px solid #1e1e2e', borderRadius: 8, padding: '20px', marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 10 }}>
                Bridge Path
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {result.bridge_path.map((node, i) => (
                  <React.Fragment key={i}>
                    <span style={{ background: '#1e1e2e', borderRadius: 6, padding: '4px 10px', fontSize: 13, color: '#9991d0' }}>
                      {typeof node === 'string' ? node : node.name || node.label || JSON.stringify(node)}
                    </span>
                    {i < result.bridge_path.length - 1 && (
                      <span style={{ color: '#6b7280', fontSize: 13 }}>→</span>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          )}

          {/* Similar papers */}
          {result.similar_papers && result.similar_papers.length > 0 && (
            <div style={{ background: '#12121e', border: '1px solid #1e1e2e', borderRadius: 8, padding: '20px' }}>
              <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 10 }}>
                Relevant Papers ({result.similar_papers.length})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {result.similar_papers.slice(0, 10).map((p, i) => (
                  <div key={i} style={{ paddingBottom: 8, borderBottom: i < Math.min(result.similar_papers.length, 10) - 1 ? '1px solid #1e1e2e' : 'none' }}>
                    {p.id ? (
                      <Link to={`/paper/${p.id}`} style={{ fontSize: 13, color: '#7c6af7' }}>
                        {p.title || `Paper ${p.id}`}
                      </Link>
                    ) : (
                      <div style={{ fontSize: 13, color: '#a0a0b8' }}>
                        {typeof p === 'string' ? p : p.title || JSON.stringify(p)}
                      </div>
                    )}
                    {p.score != null && (
                      <span style={{ fontSize: 12, color: '#6b7280' }}> — score: {p.score.toFixed(3)}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

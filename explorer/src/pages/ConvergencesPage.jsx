import React, { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { API, s, EPISTEMIC } from '../shared.js'
import { TypeTag, Loading, ErrorMsg } from '../components/ui.jsx'

export default function ConvergencesPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [minConf, setMinConf] = useState(0.7)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Try v1 endpoint first (has convergent claim text)
      const data = await fetch(`${API}/v1/convergences?min_confidence=${minConf}&limit=50`).then(r => r.json())
      setItems(data.convergences || [])
    } catch {
      setError('Cannot load convergences.')
    }
    setLoading(false)
  }, [minConf])

  useEffect(() => { load() }, [load])

  return (
    <div style={s.twoCol}>
      <aside style={s.sidebar}>
        <div style={s.sectionTitle}>Convergence Zones</div>
        <p style={{ fontSize: '12px', color: '#6b7280', lineHeight: '1.6', marginBottom: '16px' }}>
          Papers at the intersection of multiple high-confidence connections — research zones where evidence accumulates.
        </p>
        <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '6px' }}>
          Min Confidence: {(minConf * 100).toFixed(0)}%
        </div>
        <input
          type="range" min="0.5" max="1" step="0.05"
          value={minConf}
          onChange={e => setMinConf(parseFloat(e.target.value))}
          style={{ width: '100%', marginBottom: '16px', cursor: 'pointer' }}
        />
        <div style={{ fontSize: '12px', color: '#6b7280' }}>{items.length} convergence zones found</div>

        <div style={{ marginTop: '24px', padding: '12px', background: '#12121e', borderRadius: '6px', border: `1px solid ${EPISTEMIC.convergence}33` }}>
          <div style={{ fontSize: '10px', color: EPISTEMIC.convergence, fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
            What is a Convergence Zone?
          </div>
          <p style={{ fontSize: '11px', color: '#6b7280', lineHeight: '1.6', margin: 0 }}>
            A paper connected to 2+ others with high confidence — evidence that multiple research threads point to the same findings.
          </p>
        </div>
      </aside>
      <main style={s.content}>
        {error && <ErrorMsg msg={error} />}
        {loading && <Loading />}
        {!loading && items.length === 0 && (
          <div style={{ fontSize: '13px', color: '#6b7280' }}>No convergence zones at this confidence threshold.</div>
        )}
        {!loading && items.map((item, i) => {
          const avgConf = parseFloat(item.avg_confidence) || 0
          const types = Array.isArray(item.connection_types) ? item.connection_types : []
          return (
            <div key={item.id || i} style={{ ...s.card, borderLeft: `3px solid ${EPISTEMIC.convergence}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                <Link to={`/papers/${item.id}`} style={{ ...s.paperLink, flex: 1 }}>{item.title}</Link>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontSize: '22px', fontWeight: '700', color: EPISTEMIC.convergence }}>{item.connection_count}</div>
                  <div style={{ fontSize: '11px', color: '#6b7280' }}>connections</div>
                </div>
              </div>

              {/* Convergent claim */}
              {item.convergent_claim && (
                <div style={{ marginTop: '10px', padding: '8px 12px', background: '#0a1a10', borderLeft: `3px solid ${EPISTEMIC.convergence}`, borderRadius: '0 4px 4px 0' }}>
                  <div style={{ fontSize: '10px', color: EPISTEMIC.convergence, fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '3px' }}>
                    Convergent Claim
                  </div>
                  <p style={{ fontSize: '12px', color: '#a0a0b8', margin: 0, lineHeight: '1.5' }}>
                    {typeof item.convergent_claim === 'string' ? item.convergent_claim : JSON.stringify(item.convergent_claim)}
                  </p>
                </div>
              )}

              <div style={{ marginTop: '8px', display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
                {types.filter(Boolean).map(t => <TypeTag key={t} type={t} />)}
              </div>

              <div style={s.strength}>
                <div style={{ ...s.strengthBar, width: `${avgConf * 100}%`, background: EPISTEMIC.convergence }} />
              </div>
              <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                <span>Avg confidence: {(avgConf * 100).toFixed(0)}%</span>
                {item.doi && (
                  <a href={`https://doi.org/${item.doi}`} target="_blank" rel="noopener" style={{ color: '#7c6af7' }}>DOI ↗</a>
                )}
              </div>

              {/* Action buttons */}
              <div style={{ display: 'flex', gap: '8px', marginTop: '10px', flexWrap: 'wrap' }}>
                <Link
                  to={`/explore?focus=${item.id}`}
                  style={{ ...s.btnGhost, fontSize: '11px', padding: '4px 10px', textDecoration: 'none', display: 'inline-block' }}
                >
                  View in Graph
                </Link>
                <Link
                  to={`/papers/${item.id}`}
                  style={{ ...s.btnGhost, fontSize: '11px', padding: '4px 10px', textDecoration: 'none', display: 'inline-block' }}
                >
                  View Paper
                </Link>
              </div>
            </div>
          )
        })}
      </main>
    </div>
  )
}

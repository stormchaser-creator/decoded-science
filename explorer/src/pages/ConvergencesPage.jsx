import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { API, s } from '../shared.js'
import { TypeTag, Loading, ErrorMsg } from '../components/ui.jsx'

export default function ConvergencesPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [minConf, setMinConf] = useState(0.7)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetch(`${API}/connections/convergences?min_confidence=${minConf}&limit=50`).then(r => r.json())
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
            <div key={item.id || i} style={s.card}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                <Link to={`/papers/${item.id}`} style={{ ...s.paperLink, flex: 1 }}>{item.title}</Link>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontSize: '22px', fontWeight: '700', color: '#fbbf24' }}>{item.connection_count}</div>
                  <div style={{ fontSize: '11px', color: '#6b7280' }}>connections</div>
                </div>
              </div>
              <div style={{ marginTop: '8px' }}>
                {types.filter(Boolean).map(t => <TypeTag key={t} type={t} />)}
              </div>
              <div style={s.strength}>
                <div style={{ ...s.strengthBar, width: `${avgConf * 100}%`, background: '#fbbf24' }} />
              </div>
              <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
                Avg confidence: {(avgConf * 100).toFixed(0)}%
                {item.doi && (
                  <> · <a href={`https://doi.org/${item.doi}`} target="_blank" rel="noopener" style={{ color: '#7c6af7' }}>DOI ↗</a></>
                )}
              </div>
            </div>
          )
        })}
      </main>
    </div>
  )
}

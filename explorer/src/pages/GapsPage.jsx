import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { API, s } from '../shared.js'
import { Loading, ErrorMsg } from '../components/ui.jsx'
import SEO from '../components/SEO.jsx'

export default function GapsPage() {
  const [gaps, setGaps] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API}/gaps?limit=50`)
      .then(r => r.json())
      .then(d => { setGaps(d.gaps || []); setLoading(false) })
      .catch(() => { setError('Cannot load gaps.'); setLoading(false) })
  }, [])

  return (
    <div style={s.page}>
      <SEO
        title="Research Field Gaps"
        description="Identify gaps in the scientific literature — areas where connections should exist but don't, suggesting unexplored research opportunities across disciplines."
        path="/gaps"
      />
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 6px' }}>Field Gaps</h2>
        <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>
          Well-connected papers that haven't been critiqued yet — potential research opportunities or areas needing deeper analysis.
        </p>
      </div>
      {error && <ErrorMsg msg={error} />}
      {loading && <Loading />}
      {!loading && gaps.length === 0 && (
        <div style={{ fontSize: '13px', color: '#6b7280' }}>No gaps found — all well-connected papers have been critiqued.</div>
      )}
      {!loading && gaps.map((gap, i) => (
        <div key={gap.id || i} style={s.card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
            <div style={{ flex: 1 }}>
              <Link to={`/papers/${gap.id}`} style={s.paperLink}>{gap.title}</Link>
              <div style={s.paperMeta}>
                {gap.journal && <span>{gap.journal} · </span>}
                {gap.published_date && <span>{String(gap.published_date).slice(0, 4)}</span>}
              </div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontSize: '20px', fontWeight: '700', color: '#f87171' }}>{gap.connection_count}</div>
              <div style={{ fontSize: '11px', color: '#6b7280' }}>connections</div>
            </div>
          </div>
          <div style={{ marginTop: '8px' }}>
            <span style={{ ...s.tag, ...s.tagYellow }}>{gap.connection_count} connections</span>
            <span style={{ ...s.tag, ...s.tagRed }}>no critique</span>
            <span style={{ ...s.tag, ...(gap.status === 'extracted' || gap.status === 'connected' ? s.tagGreen : {}) }}>
              {gap.status}
            </span>
          </div>
          <div style={{ marginTop: '10px' }}>
            <Link to="/analyze" style={{ ...s.btnOutline, fontSize: '11px', padding: '3px 10px' }}>
              Analyze →
            </Link>
          </div>
        </div>
      ))}
    </div>
  )
}

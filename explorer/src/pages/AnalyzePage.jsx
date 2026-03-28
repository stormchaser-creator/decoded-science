import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { API, s } from '../shared.js'
import { ErrorMsg } from '../components/ui.jsx'

export default function AnalyzePage() {
  const [doi, setDoi] = useState('')
  const [priority, setPriority] = useState(1)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const submit = async e => {
    e.preventDefault()
    if (!doi.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const res = await fetch(`${API}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doi: doi.trim(), priority }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Analysis failed')
      setResult(data)
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }

  return (
    <div style={s.page}>
      <div style={{ maxWidth: '640px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 6px' }}>On-demand Analysis</h2>
        <p style={{ fontSize: '13px', color: '#6b7280', marginBottom: '24px' }}>
          Submit a DOI to trigger full AI extraction and connection discovery. The paper will be fetched, extracted, and added to the connectome.
        </p>
        {error && <ErrorMsg msg={error} />}
        {result && (
          <div style={{ ...s.successBanner, marginBottom: '16px' }}>
            Analysis submitted successfully.
            {result.paper_id && (
              <> · <Link to={`/papers/${result.paper_id}`} style={{ color: '#4ade80', fontWeight: '600' }}>View paper →</Link></>
            )}
          </div>
        )}
        <div style={s.card}>
          <form onSubmit={submit}>
            <label style={s.label}>DOI</label>
            <input
              style={s.input}
              placeholder="10.1016/j.cell.2024.01.001"
              value={doi}
              onChange={e => setDoi(e.target.value)}
            />
            <label style={s.label}>Priority (1 = high, 0 = normal)</label>
            <input
              style={s.input}
              type="number"
              min="0"
              max="10"
              value={priority}
              onChange={e => setPriority(parseInt(e.target.value, 10))}
            />
            <button style={{ ...s.btn, padding: '10px 24px' }} type="submit" disabled={loading || !doi.trim()}>
              {loading ? 'Submitting…' : 'Analyze DOI'}
            </button>
          </form>
        </div>

        {loading && (
          <div style={{ ...s.card, marginTop: '16px', textAlign: 'center', color: '#6b7280', padding: '32px' }}>
            <div style={{ fontSize: '24px', marginBottom: '8px' }}>⚙️</div>
            <div>Analysis queued — runs in background.</div>
            <div style={{ fontSize: '12px', marginTop: '6px', color: '#4b4b6b' }}>
              Fetching paper, running extraction, discovering connections…
            </div>
          </div>
        )}

        <div style={{ ...s.card, marginTop: '24px' }}>
          <div style={s.sectionTitle}>How it works</div>
          <div style={{ display: 'grid', gap: '10px' }}>
            {[
              ['1', 'Fetch', 'Paper metadata and full text retrieved from DOI'],
              ['2', 'Extract', 'AI extracts entities, claims, mechanisms, and findings'],
              ['3', 'Connect', 'Graph discovery finds connections to existing papers'],
              ['4', 'Critique', 'Intelligence brief generated with quality assessment'],
            ].map(([n, title, desc]) => (
              <div key={n} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                <div style={{ ...s.tag, ...s.tagPurple, flexShrink: 0, minWidth: '20px', textAlign: 'center', marginTop: 0 }}>{n}</div>
                <div>
                  <span style={{ fontSize: '13px', fontWeight: '600', color: '#9991d0' }}>{title}: </span>
                  <span style={{ fontSize: '13px', color: '#6b7280' }}>{desc}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

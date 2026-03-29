import React, { useState, useEffect, useRef } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { API, s } from '../shared.js'
import { ErrorMsg } from '../components/ui.jsx'
import SEO from '../components/SEO.jsx'

const STAGES = [
  { key: 'fetching', label: 'Fetching paper from DOI', icon: '🌐' },
  { key: 'extracting', label: 'Running AI extraction', icon: '🧠' },
  { key: 'connecting', label: 'Discovering connections', icon: '🔗' },
  { key: 'critiquing', label: 'Generating intelligence brief', icon: '📊' },
  { key: 'done', label: 'Complete', icon: '✓' },
  { key: 'already_ingested', label: 'Already in database', icon: '✓' },
]

function ProgressBar({ stage, status }) {
  const stageKeys = STAGES.map(s => s.key)
  const currentIdx = stageKeys.indexOf(stage)

  return (
    <div style={{ marginTop: '16px' }}>
      {STAGES.filter(s => !['done', 'already_ingested'].includes(s.key)).map((st, i) => {
        const isDone = status === 'complete' || i < currentIdx
        const isActive = st.key === stage && status === 'running'
        return (
          <div key={st.key} style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
            <div style={{
              width: '28px', height: '28px', borderRadius: '50%',
              background: isDone ? '#4ade80' : isActive ? '#7c6af7' : '#1e1e2e',
              border: `2px solid ${isDone ? '#4ade80' : isActive ? '#7c6af7' : '#2e2e4e'}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '14px', flexShrink: 0, transition: 'all 0.3s',
            }}>
              {isDone ? '✓' : st.icon}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '13px', color: isDone ? '#4ade80' : isActive ? '#e0e0e8' : '#4b5563' }}>
                {st.label}
                {isActive && <span style={{ marginLeft: '8px', animation: 'pulse 1.5s infinite' }}>…</span>}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function AnalyzePage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [doi, setDoi] = useState(searchParams.get('doi') || '')
  const [priority, setPriority] = useState(1)
  const [loading, setLoading] = useState(false)
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const pollInterval = useRef(null)

  const stopPolling = () => {
    if (pollInterval.current) {
      clearInterval(pollInterval.current)
      pollInterval.current = null
    }
  }

  const pollJob = async (jobId) => {
    try {
      const data = await fetch(`${API}/v1/papers/analyze/${jobId}`).then(r => r.json())
      setJob(data)
      if (data.status === 'complete' || data.status === 'failed') {
        stopPolling()
        setLoading(false)
        if (data.status === 'complete' && data.paper_id) {
          setTimeout(() => navigate(`/papers/${data.paper_id}`), 1500)
        }
      }
    } catch {
      // Keep polling on network errors
    }
  }

  useEffect(() => () => stopPolling(), [])

  const submit = async e => {
    e.preventDefault()
    if (!doi.trim()) return
    setLoading(true)
    setJob(null)
    setError(null)
    try {
      const res = await fetch(`${API}/v1/papers/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doi: doi.trim(), priority }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Analysis failed')
      setJob(data)
      // Start polling
      const jobId = data.job_id
      pollInterval.current = setInterval(() => pollJob(jobId), 2000)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const isComplete = job?.status === 'complete'
  const isFailed = job?.status === 'failed'

  return (
    <div style={s.page}>
      <SEO
        title="Analyze a Paper"
        description="Submit a research paper for AI-powered analysis. Extract entities, map connections to the existing knowledge graph, and discover what the literature knows that the paper alone can't see."
        path="/analyze"
      />
      <div style={{ maxWidth: '640px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 6px' }}>On-demand Analysis</h2>
        <p style={{ fontSize: '13px', color: '#6b7280', marginBottom: '24px' }}>
          Submit a DOI to trigger full AI extraction and connection discovery. Track progress in real-time.
        </p>
        {error && <ErrorMsg msg={error} />}

        {isComplete && (
          <div style={{ ...s.successBanner, marginBottom: '16px' }}>
            Analysis complete!
            {job.paper_id && (
              <> · <Link to={`/papers/${job.paper_id}`} style={{ color: '#4ade80', fontWeight: '600' }}>View paper →</Link></>
            )}
            <div style={{ fontSize: '12px', marginTop: '4px', opacity: 0.8 }}>Redirecting to paper…</div>
          </div>
        )}

        {isFailed && (
          <div style={{ ...s.errorBanner, marginBottom: '16px' }}>
            Analysis failed: {job.error || 'Unknown error'}
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
              disabled={loading}
            />
            <label style={s.label}>Priority (1 = high, 0 = normal)</label>
            <input
              style={s.input}
              type="number"
              min="0"
              max="10"
              value={priority}
              onChange={e => setPriority(parseInt(e.target.value, 10))}
              disabled={loading}
            />
            <button style={{ ...s.btn, padding: '10px 24px', opacity: loading ? 0.6 : 1 }} type="submit" disabled={loading || !doi.trim()}>
              {loading ? 'Analyzing…' : 'Analyze DOI'}
            </button>
          </form>
        </div>

        {/* Progress indicator */}
        {loading && job && (
          <div style={{ ...s.card, marginTop: '16px' }}>
            <div style={{ fontSize: '13px', fontWeight: '600', color: '#9991d0', marginBottom: '4px' }}>
              {job.doi}
            </div>
            <div style={{ fontSize: '11px', color: '#6b7280', marginBottom: '8px' }}>
              Job ID: {job.job_id?.substring(0, 8)}…
            </div>
            <ProgressBar stage={job.stage} status={job.status} />
          </div>
        )}

        {/* How it works */}
        <div style={{ ...s.card, marginTop: '24px' }}>
          <div style={s.sectionTitle}>How it works</div>
          <div style={{ display: 'grid', gap: '10px' }}>
            {[
              ['1', 'Fetch', 'Paper metadata and full text retrieved from DOI via CrossRef'],
              ['2', 'Extract', 'AI extracts entities, claims, mechanisms, and key findings'],
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

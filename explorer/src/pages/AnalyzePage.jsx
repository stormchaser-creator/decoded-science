import React, { useState, useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { API, s } from '../shared.js'
import { ErrorMsg } from '../components/ui.jsx'

const CONN_COLORS = {
  supports: '#4ade80',
  contradicts: '#f87171',
  extends: '#7c6af7',
  mechanism_for: '#facc15',
  convergent_evidence: '#60a5fa',
  methodological_parallel: '#a78bfa',
}

const CONN_LABELS = {
  supports: 'Supports',
  contradicts: 'Contradicts',
  extends: 'Extends',
  mechanism_for: 'Mechanism for',
  convergent_evidence: 'Convergent evidence',
  methodological_parallel: 'Methodological parallel',
}

const QUALITY_COLORS = { high: '#4ade80', medium: '#facc15', low: '#f87171' }
const REC_LABELS = {
  read: 'Must read',
  skim: 'Skim',
  skip: 'Skip',
  replicate: 'Worth replicating',
  build_on: 'Build on this',
}

const STAGES = [
  { key: 'fetching',   label: 'Fetching paper' },
  { key: 'extracting', label: 'AI extraction' },
  { key: 'done',       label: 'Corpus connections + brief' },
]

function ProgressBar({ stage, status }) {
  const keys = STAGES.map(s => s.key)
  const idx = keys.indexOf(stage)
  return (
    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', margin: '16px 0' }}>
      {STAGES.map((st, i) => {
        const done = status === 'complete' || i < idx
        const active = st.key === stage && status === 'running'
        return (
          <React.Fragment key={st.key}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{
                width: '22px', height: '22px', borderRadius: '50%', flexShrink: 0,
                background: done ? '#4ade80' : active ? '#7c6af7' : '#1e1e2e',
                border: `2px solid ${done ? '#4ade80' : active ? '#7c6af7' : '#2e2e4e'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '11px', transition: 'all 0.3s',
              }}>
                {done ? '✓' : i + 1}
              </div>
              <span style={{ fontSize: '12px', color: done ? '#4ade80' : active ? '#e0e0e8' : '#4b5563', whiteSpace: 'nowrap' }}>
                {st.label}{active && '…'}
              </span>
            </div>
            {i < STAGES.length - 1 && (
              <div style={{ flex: 1, height: '2px', background: i < idx ? '#4ade80' : '#2e2e4e', minWidth: '20px' }} />
            )}
          </React.Fragment>
        )
      })}
    </div>
  )
}

function ScoreBadge({ label, value }) {
  const pct = Math.round((value / 10) * 100)
  const color = pct >= 70 ? '#4ade80' : pct >= 40 ? '#facc15' : '#f87171'
  return (
    <div style={{ textAlign: 'center', minWidth: '70px' }}>
      <div style={{ fontSize: '20px', fontWeight: '700', color }}>{value?.toFixed(1)}</div>
      <div style={{ fontSize: '10px', color: '#6b7280', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
    </div>
  )
}

function IntelligenceBrief({ brief, paperId }) {
  if (!brief) return null
  const qColor = QUALITY_COLORS[brief.overall_quality] || '#6b7280'
  return (
    <div style={{ ...s.card, marginTop: '16px', borderLeft: `3px solid ${qColor}` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
        <div>
          <div style={{ fontSize: '11px', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '4px' }}>Intelligence Brief</div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <span style={{ background: qColor, color: '#0a0a14', fontSize: '10px', fontWeight: '700', padding: '2px 8px', borderRadius: '4px', textTransform: 'uppercase' }}>
              {brief.overall_quality}
            </span>
            <span style={{ fontSize: '12px', color: '#9991d0' }}>{REC_LABELS[brief.recommendation] || brief.recommendation}</span>
          </div>
        </div>
        <Link to={`/papers/${paperId}`} style={{ fontSize: '12px', color: '#7c6af7', textDecoration: 'none' }}>
          Full paper →
        </Link>
      </div>

      <p style={{ fontSize: '14px', color: '#c8c8d8', lineHeight: '1.6', margin: '0 0 16px' }}>
        {brief.summary}
      </p>

      <div style={{ display: 'flex', gap: '24px', padding: '12px 0', borderTop: '1px solid #1e1e2e', borderBottom: '1px solid #1e1e2e', marginBottom: '16px', flexWrap: 'wrap' }}>
        <ScoreBadge label="Methodology" value={brief.methodology_score} />
        <ScoreBadge label="Novelty" value={brief.novelty_score} />
        <ScoreBadge label="Rigor" value={brief.statistical_rigor} />
        <ScoreBadge label="Reproducibility" value={brief.reproducibility_score} />
      </div>

      {brief.strengths?.length > 0 && (
        <div style={{ marginBottom: '10px' }}>
          <div style={{ fontSize: '11px', color: '#4ade80', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>Strengths</div>
          {brief.strengths.map((s, i) => (
            <div key={i} style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '3px' }}>✓ {s}</div>
          ))}
        </div>
      )}

      {brief.weaknesses?.length > 0 && (
        <div style={{ marginBottom: '10px' }}>
          <div style={{ fontSize: '11px', color: '#facc15', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>Weaknesses</div>
          {brief.weaknesses.map((w, i) => (
            <div key={i} style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '3px' }}>⚠ {w}</div>
          ))}
        </div>
      )}

      {brief.red_flags?.length > 0 && (
        <div>
          <div style={{ fontSize: '11px', color: '#f87171', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>Red Flags</div>
          {brief.red_flags.map((r, i) => (
            <div key={i} style={{ fontSize: '12px', color: '#f87171', marginBottom: '3px' }}>✗ {r}</div>
          ))}
        </div>
      )}
    </div>
  )
}

function ConnectionCard({ conn }) {
  const color = CONN_COLORS[conn.connection_type] || '#6b7280'
  const label = CONN_LABELS[conn.connection_type] || conn.connection_type
  return (
    <div style={{ padding: '12px', background: '#0f0f1a', borderRadius: '8px', borderLeft: `3px solid ${color}` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px', marginBottom: '6px' }}>
        <div style={{ flex: 1 }}>
          <span style={{ fontSize: '10px', color, textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: '700' }}>{label}</span>
          {conn.doi
            ? <Link to={`/papers/${conn.paper_id}`} style={{ display: 'block', fontSize: '13px', color: '#e0e0e8', fontWeight: '500', marginTop: '3px', textDecoration: 'none' }}>
                {conn.title}
              </Link>
            : <div style={{ fontSize: '13px', color: '#e0e0e8', fontWeight: '500', marginTop: '3px' }}>{conn.title}</div>
          }
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: '11px', color: '#6b7280' }}>{Math.round((conn.confidence || 0) * 100)}% conf.</div>
          {conn.journal && <div style={{ fontSize: '10px', color: '#4b5563', marginTop: '2px' }}>{conn.journal}</div>}
        </div>
      </div>
      <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0 0 4px', lineHeight: '1.5' }}>{conn.description}</p>
      {conn.novelty_note && (
        <p style={{ fontSize: '11px', color: '#7c6af7', margin: 0, fontStyle: 'italic' }}>{conn.novelty_note}</p>
      )}
      {conn.shared_concepts?.length > 0 && (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '6px' }}>
          {conn.shared_concepts.map((c, i) => (
            <span key={i} style={{ fontSize: '10px', background: '#1e1e2e', color: '#6b7280', padding: '2px 6px', borderRadius: '3px' }}>{c}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function ConnectionsSummary({ connections }) {
  if (!connections?.length) return (
    <div style={{ ...s.card, marginTop: '16px' }}>
      <div style={s.sectionTitle}>Corpus Connections</div>
      <p style={{ fontSize: '13px', color: '#6b7280', margin: 0 }}>
        No connections found in current corpus. This may indicate a novel topic or limited corpus coverage.
      </p>
    </div>
  )

  const byType = connections.reduce((acc, c) => {
    acc[c.connection_type] = (acc[c.connection_type] || 0) + 1
    return acc
  }, {})

  return (
    <div style={{ ...s.card, marginTop: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div style={s.sectionTitle}>Corpus Connections ({connections.length})</div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {Object.entries(byType).map(([type, count]) => (
            <span key={type} style={{ fontSize: '10px', color: CONN_COLORS[type] || '#6b7280', background: '#1e1e2e', padding: '2px 6px', borderRadius: '3px' }}>
              {count} {CONN_LABELS[type] || type}
            </span>
          ))}
        </div>
      </div>
      <div style={{ display: 'grid', gap: '8px' }}>
        {connections.map((c, i) => <ConnectionCard key={i} conn={c} />)}
      </div>
    </div>
  )
}

export default function AnalyzePage() {
  const [searchParams] = useSearchParams()
  const [doi, setDoi] = useState(searchParams.get('doi') || '')
  const [loading, setLoading] = useState(false)
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)
  const pollInterval = useRef(null)

  const stopPolling = () => {
    if (pollInterval.current) { clearInterval(pollInterval.current); pollInterval.current = null }
  }

  const pollJob = async (jobId) => {
    try {
      const data = await fetch(`${API}/v1/papers/analyze/${jobId}`).then(r => r.json())
      setJob(data)
      if (data.status === 'complete' || data.status === 'failed') {
        stopPolling()
        setLoading(false)
      }
    } catch { /* keep polling */ }
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
        body: JSON.stringify({ doi: doi.trim(), priority: 1 }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Analysis failed')
      setJob(data)
      pollInterval.current = setInterval(() => pollJob(data.job_id), 2000)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const isComplete = job?.status === 'complete'
  const isFailed = job?.status === 'failed'

  return (
    <div style={s.page}>
      <div style={{ maxWidth: '760px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 4px' }}>On-demand Analysis</h2>
        <p style={{ fontSize: '13px', color: '#6b7280', marginBottom: '20px' }}>
          Submit a DOI — the system fetches the paper, extracts claims, searches {'{'}18K+{'}'} papers in the corpus for connections, and generates a contextualized intelligence brief.
        </p>

        {error && <ErrorMsg msg={error} />}

        <div style={s.card}>
          <form onSubmit={submit} style={{ display: 'flex', gap: '10px', alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <label style={s.label}>DOI</label>
              <input
                style={s.input}
                placeholder="10.1016/j.cell.2024.01.001"
                value={doi}
                onChange={e => setDoi(e.target.value)}
                disabled={loading}
              />
            </div>
            <button
              style={{ ...s.btn, padding: '10px 20px', marginBottom: '0', opacity: loading ? 0.6 : 1, whiteSpace: 'nowrap' }}
              type="submit"
              disabled={loading || !doi.trim()}
            >
              {loading ? 'Analyzing…' : 'Analyze DOI'}
            </button>
          </form>
        </div>

        {/* Progress */}
        {(loading || job) && !isComplete && !isFailed && (
          <div style={{ ...s.card, marginTop: '12px' }}>
            <div style={{ fontSize: '12px', color: '#9991d0', marginBottom: '4px' }}>{job?.doi}</div>
            <ProgressBar stage={job?.stage} status={job?.status} />
          </div>
        )}

        {/* Failure */}
        {isFailed && (
          <div style={{ ...s.errorBanner, marginTop: '12px' }}>
            {job.error || 'Analysis failed'}
          </div>
        )}

        {/* Intelligence Report */}
        {isComplete && (
          <>
            <div style={{ ...s.successBanner, marginTop: '12px' }}>
              Analysis complete
              {job.connection_count > 0 && ` · ${job.connection_count} corpus connections found`}
              {job.paper_id && (
                <> · <Link to={`/papers/${job.paper_id}`} style={{ color: '#4ade80', fontWeight: '600' }}>Full paper page →</Link></>
              )}
            </div>

            <IntelligenceBrief brief={job.brief} paperId={job.paper_id} />
            <ConnectionsSummary connections={job.connections} />
          </>
        )}

        {/* How it works (only show before analysis) */}
        {!job && (
          <div style={{ ...s.card, marginTop: '20px' }}>
            <div style={s.sectionTitle}>What you get</div>
            <div style={{ display: 'grid', gap: '8px' }}>
              {[
                ['Fetch', 'Full text retrieved via CrossRef, Semantic Scholar, PubMed, and publisher page scraping'],
                ['Extract', 'AI pulls entities, claims, mechanisms, and key findings from the paper'],
                ['Connect', 'Searched against 18K+ papers in corpus — finds papers that support, contradict, or extend the findings'],
                ['Brief', 'Intelligence brief: quality scores, strengths/weaknesses, and how this paper fits the existing evidence base'],
              ].map(([title, desc], i) => (
                <div key={i} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                  <div style={{ ...s.tag, ...s.tagPurple, flexShrink: 0, minWidth: '20px', textAlign: 'center', marginTop: 0 }}>{i + 1}</div>
                  <div>
                    <span style={{ fontSize: '13px', fontWeight: '600', color: '#9991d0' }}>{title}: </span>
                    <span style={{ fontSize: '13px', color: '#6b7280' }}>{desc}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

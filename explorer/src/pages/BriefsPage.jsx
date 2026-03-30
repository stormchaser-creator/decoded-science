import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { API, s, parseJsonField } from '../shared.js'
import { Loading, ErrorMsg } from '../components/ui.jsx'
import SEO from '../components/SEO.jsx'

const VIEWS = [
  { key: '', label: 'All Briefs', icon: '\u{1F4CB}' },
  { key: 'must-reads', label: 'Must Reads', icon: '\u{2B50}' },
  { key: 'controversies', label: 'Controversies', icon: '\u{26A1}' },
  { key: 'hubs', label: 'Hub Papers', icon: '\u{1F578}' },
  { key: 'recent', label: 'Recent', icon: '\u{1F551}' },
]

const SORT_OPTIONS = [
  { key: 'methodology', label: 'Methodology' },
  { key: 'novelty', label: 'Novelty' },
  { key: 'connections', label: 'Connections' },
  { key: 'date', label: 'Date' },
]

const TOPIC_COLORS = {
  aging: '#c084fc', neurodegeneration: '#f87171', inflammation: '#fb923c',
  metabolism: '#fbbf24', microbiome: '#4ade80', exercise: '#34d399',
  nutrition: '#a3e635', immunology: '#60a5fa', epigenetics: '#818cf8',
  cancer: '#f43f5e', cardiovascular: '#f97316', 'stem-cells': '#2dd4bf',
  autophagy: '#a78bfa', sleep: '#94a3b8', stress: '#fb7185',
}

function QualityBadge({ score }) {
  const q = (score || '').toLowerCase()
  if (q === 'high') return <span style={{ ...s.tag, ...s.tagGreen, marginTop: 0, fontWeight: '700' }}>HIGH</span>
  if (q === 'medium') return <span style={{ ...s.tag, ...s.tagYellow, marginTop: 0, fontWeight: '700' }}>MED</span>
  return <span style={{ ...s.tag, ...s.tagRed, marginTop: 0, fontWeight: '700' }}>LOW</span>
}

function TopicPill({ topic, selected, onClick }) {
  const color = TOPIC_COLORS[topic] || '#7c6af7'
  return (
    <button onClick={onClick} style={{
      background: selected ? color + '22' : 'transparent',
      border: `1px solid ${selected ? color : '#2d2060'}`,
      color: selected ? color : '#6b7280',
      borderRadius: '14px', padding: '3px 10px', fontSize: '12px',
      cursor: 'pointer', fontWeight: selected ? '600' : '400',
      transition: 'all 0.15s', whiteSpace: 'nowrap',
    }}>
      {topic}
    </button>
  )
}

export default function BriefsPage() {
  const [briefs, setBriefs] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState({})
  const [skip, setSkip] = useState(0)
  const [view, setView] = useState('')
  const [topic, setTopic] = useState('')
  const [sort, setSort] = useState('methodology')
  const [topics, setTopics] = useState([])

  // Load topics on mount
  useEffect(() => {
    fetch(`${API}/v1/briefs/topics`).then(r => r.json()).then(d => setTopics(d.topics || [])).catch(() => {})
  }, [])

  const load = useCallback(async (offset = 0) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: '20', skip: String(offset), sort })
      if (view) params.set('view', view)
      if (topic) params.set('topic', topic)
      const data = await fetch(`${API}/v1/briefs?${params}`).then(r => r.json())
      setBriefs(data.critiques || [])
      setTotal(data.total || 0)
    } catch {
      setError('Cannot load intelligence briefs.')
    }
    setLoading(false)
  }, [view, topic, sort])

  useEffect(() => { setSkip(0); load(0) }, [view, topic, sort])
  useEffect(() => { load(skip) }, [skip])

  const toggle = key => setExpanded(p => ({ ...p, [key]: !p[key] }))

  return (
    <div style={s.page}>
      <SEO title="Intelligence Briefs" description="AI-generated intelligence briefs with deep corpus analysis." path="/briefs" />

      {/* Header */}
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '22px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 6px' }}>Intelligence Briefs</h2>
        <p style={{ fontSize: '14px', color: '#6b7280', margin: 0 }}>
          Corpus-aware analysis of research papers.
          {total > 0 && ` ${total.toLocaleString()} briefs.`}
        </p>
      </div>

      {/* View tabs */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '14px', flexWrap: 'wrap' }}>
        {VIEWS.map(v => (
          <button key={v.key} onClick={() => setView(v.key)} style={{
            background: view === v.key ? '#7c6af7' : '#1e1e2e',
            color: view === v.key ? '#fff' : '#9991d0',
            border: 'none', borderRadius: '6px', padding: '6px 14px', fontSize: '13px',
            cursor: 'pointer', fontWeight: view === v.key ? '600' : '400',
            display: 'flex', alignItems: 'center', gap: '6px',
          }}>
            <span>{v.icon}</span> {v.label}
          </button>
        ))}
      </div>

      {/* Topic filter + Sort */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', flex: 1 }}>
          {topic && (
            <button onClick={() => setTopic('')} style={{
              background: '#7c6af722', border: '1px solid #7c6af7', color: '#7c6af7',
              borderRadius: '14px', padding: '3px 10px', fontSize: '12px', cursor: 'pointer', fontWeight: '600',
            }}>
              {topic} ✕
            </button>
          )}
          {topics.filter(t => t.topic !== topic).slice(0, topic ? 8 : 12).map(t => (
            <TopicPill key={t.topic} topic={t.topic} selected={false} onClick={() => setTopic(t.topic)} />
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
          <span style={{ fontSize: '12px', color: '#4b4b6b' }}>Sort:</span>
          <select value={sort} onChange={e => setSort(e.target.value)} style={{
            background: '#1e1e2e', color: '#9991d0', border: '1px solid #2d2060',
            borderRadius: '6px', padding: '4px 8px', fontSize: '12px', cursor: 'pointer',
          }}>
            {SORT_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select>
        </div>
      </div>

      {/* View description */}
      {view && (
        <div style={{ background: '#1a1a2e', borderRadius: '6px', padding: '10px 14px', marginBottom: '14px', fontSize: '13px', color: '#9991d0' }}>
          {view === 'must-reads' && 'Papers rated high quality with the highest novelty scores — the ones worth reading in full.'}
          {view === 'controversies' && 'Papers involved in contradictions — where the science is actively debated.'}
          {view === 'hubs' && 'The most connected papers in the corpus — field-defining works that everything else references.'}
          {view === 'recent' && 'Most recently assessed papers.'}
        </div>
      )}

      {error && <ErrorMsg msg={error} />}
      {loading && <Loading />}
      {!loading && briefs.length === 0 && (
        <div style={{ fontSize: '14px', color: '#6b7280', padding: '40px', textAlign: 'center' }}>
          No briefs found for this filter combination.
        </div>
      )}

      {/* Brief cards */}
      {!loading && briefs.map((b, i) => {
        const key = b.id || i
        const isOpen = expanded[key]
        const qualityLabel = b.overall_quality || ''
        const novelty = parseFloat(b.novelty_score) || 0
        const methodology = parseFloat(b.methodology_score) || 0
        const connCount = b.connection_count || 0
        const paperTopics = b.topic_tags || []

        return (
          <div key={key} style={s.card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '4px' }}>
                  <Link to={`/papers/${b.paper_id}`} style={s.paperLink}>{b.paper_title}</Link>
                  <QualityBadge score={b.overall_quality} />
                  {b.recommendation && b.recommendation !== 'skim' && (
                    <span style={{ ...s.tag, ...s.tagBlue, marginTop: 0, fontSize: '11px', textTransform: 'uppercase' }}>
                      {b.recommendation}
                    </span>
                  )}
                </div>
                <div style={s.paperMeta}>
                  {b.journal && <span>{b.journal} · </span>}
                  {b.published_date && <span>{String(b.published_date).slice(0, 4)} · </span>}
                  {connCount > 0 && <span>{connCount} connections · </span>}
                  {b.created_at && <span>Assessed {b.created_at.slice(0, 10)}</span>}
                </div>
                {/* Topic tags */}
                {paperTopics.length > 0 && (
                  <div style={{ display: 'flex', gap: '4px', marginTop: '6px', flexWrap: 'wrap' }}>
                    {paperTopics.map(t => (
                      <span key={t} onClick={() => setTopic(t)} style={{
                        fontSize: '10px', padding: '1px 7px', borderRadius: '10px', cursor: 'pointer',
                        background: (TOPIC_COLORS[t] || '#7c6af7') + '18',
                        color: TOPIC_COLORS[t] || '#7c6af7',
                        border: `1px solid ${(TOPIC_COLORS[t] || '#7c6af7')}33`,
                      }}>
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: '16px', flexShrink: 0 }}>
                {methodology > 0 && (
                  <div style={{ textAlign: 'center', minWidth: '40px' }}>
                    <div style={{ fontSize: '20px', fontWeight: '700', color: methodology >= 7 ? '#4ade80' : methodology >= 5 ? '#fbbf24' : '#f87171' }}>
                      {methodology.toFixed(1)}
                    </div>
                    <div style={{ fontSize: '10px', color: '#6b7280' }}>method</div>
                  </div>
                )}
                {novelty > 0 && (
                  <div style={{ textAlign: 'center', minWidth: '40px' }}>
                    <div style={{ fontSize: '20px', fontWeight: '700', color: '#60a5fa' }}>
                      {novelty.toFixed(1)}
                    </div>
                    <div style={{ fontSize: '10px', color: '#6b7280' }}>novelty</div>
                  </div>
                )}
              </div>
            </div>

            {b.brief && (
              <p style={{ fontSize: '14px', color: '#a0a0b8', marginTop: '10px', lineHeight: '1.7', marginBottom: 0,
                display: isOpen ? 'block' : '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: isOpen ? 'visible' : 'hidden' }}>
                {b.brief}
              </p>
            )}

            {isOpen && (
              <div style={{ marginTop: '12px', borderTop: '1px solid #1e1e2e', paddingTop: '12px' }}>
                {b.strengths && (
                  <div style={{ marginBottom: '10px' }}>
                    <div style={{ fontSize: '12px', color: '#4ade80', fontWeight: '600', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Strengths</div>
                    <p style={{ fontSize: '13px', color: '#a0a0b8', margin: 0, lineHeight: '1.7' }}>{typeof b.strengths === 'string' ? b.strengths : JSON.stringify(b.strengths)}</p>
                  </div>
                )}
                {b.weaknesses && (
                  <div>
                    <div style={{ fontSize: '12px', color: '#fb923c', fontWeight: '600', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Weaknesses</div>
                    <p style={{ fontSize: '13px', color: '#a0a0b8', margin: 0, lineHeight: '1.7' }}>{typeof b.weaknesses === 'string' ? b.weaknesses : JSON.stringify(b.weaknesses)}</p>
                  </div>
                )}
              </div>
            )}

            <div style={{ marginTop: '10px' }}>
              <button style={{ ...s.btnGhost, padding: '4px 12px', fontSize: '12px' }} onClick={() => toggle(key)}>
                {isOpen ? 'Hide full brief \u2191' : 'Show full brief \u2193'}
              </button>
            </div>
          </div>
        )
      })}

      {total > 20 && (
        <div style={s.paginationRow}>
          <button style={{ ...s.btnOutline, opacity: skip === 0 ? 0.4 : 1 }} disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - 20))}>Prev</button>
          <span>Page {Math.floor(skip / 20) + 1} of {Math.ceil(total / 20)}</span>
          <button style={{ ...s.btnOutline, opacity: skip + 20 >= total ? 0.4 : 1 }} disabled={skip + 20 >= total} onClick={() => setSkip(skip + 20)}>Next</button>
        </div>
      )}
    </div>
  )
}

import React, { useState, useEffect, useCallback, useRef, Suspense } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { API, s, useIsMobile } from '../shared.js'
import { TypeTag, StrengthBar, Loading, ErrorMsg } from '../components/ui.jsx'
import SEO from '../components/SEO.jsx'

const ForceGraph2D = React.lazy(() => import('react-force-graph-2d'))

const CONNECTION_TYPES = [
  'contradicts', 'extends', 'mechanism_for',
  'shares_target', 'methodological_parallel', 'convergent_evidence',
]

const EDGE_COLORS = {
  contradicts: '#f43f5e',
  extends: '#10b981',
  mechanism_for: '#3b82f6',
  shares_target: '#c084fc',
  methodological_parallel: '#94a3b8',
  convergent_evidence: '#f59e0b',
  default: '#4b5563',
}

function getEdgeColor(link) {
  return EDGE_COLORS[link.type] || EDGE_COLORS.default
}

// Mini 2-node graph for the focused connection
function ConnectionGraph({ connection }) {
  const graphRef = useRef(null)
  const graphData = {
    nodes: [
      { id: connection.paper_a_id, label: (connection.paper_a_title || '').substring(0, 45), val: 8, side: 'a' },
      { id: connection.paper_b_id, label: (connection.paper_b_title || '').substring(0, 45), val: 8, side: 'b' },
    ],
    links: [
      { source: connection.paper_a_id, target: connection.paper_b_id, type: connection.connection_type, confidence: connection.confidence || 0.5 },
    ],
  }

  return (
    <div style={{ borderRadius: '8px', overflow: 'hidden', background: '#0a0a0f', border: '1px solid #2e2e4e', height: '220px' }}>
      <Suspense fallback={<div style={{ height: '220px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280', fontSize: '13px' }}>Loading graph…</div>}>
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          width={560}
          height={220}
          backgroundColor="#0a0a0f"
          nodeColor={() => '#7c6af7'}
          nodeVal={n => n.val}
          nodeLabel={n => n.label}
          linkColor={l => getEdgeColor(l)}
          linkWidth={l => Math.max(2, (l.confidence || 0.5) * 4)}
          linkDirectionalParticles={3}
          linkDirectionalParticleWidth={2}
          linkDirectionalParticleColor={l => getEdgeColor(l)}
          enableZoomInteraction={false}
          enablePanInteraction={false}
          enableNodeDrag={false}
          cooldownTicks={80}
          nodeCanvasObjectMode={() => 'after'}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const label = node.label || ''
            const maxWidth = 120
            const fontSize = 10
            ctx.font = `${fontSize}px Sans-Serif`

            // Word-wrap the label
            const words = label.split(' ')
            const lines = []
            let line = ''
            for (const word of words) {
              const test = line ? `${line} ${word}` : word
              if (ctx.measureText(test).width > maxWidth && line) {
                lines.push(line)
                line = word
              } else {
                line = test
              }
            }
            if (line) lines.push(line)

            const lineHeight = fontSize + 2
            const totalHeight = lines.length * lineHeight
            const startY = node.y + 12 + 4

            ctx.fillStyle = 'rgba(180, 180, 210, 0.9)'
            ctx.textAlign = 'center'
            lines.forEach((l, i) => {
              ctx.fillText(l, node.x, startY + i * lineHeight)
            })
          }}
          onEngineStop={() => {
            if (graphRef.current) graphRef.current.zoomToFit(200, 60)
          }}
        />
      </Suspense>
    </div>
  )
}

// Focused connection panel (shown when ?c=<uuid> is in URL)
function FocusedConnectionPanel({ connectionId, onClear }) {
  const [connection, setConnection] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    setLoading(true)
    setNotFound(false)
    fetch(`${API}/connections/${connectionId}`)
      .then(r => {
        if (r.status === 404) { setNotFound(true); setLoading(false); return null }
        return r.json()
      })
      .then(data => {
        if (data) setConnection(data)
        setLoading(false)
      })
      .catch(() => { setNotFound(true); setLoading(false) })
  }, [connectionId])

  if (loading) return (
    <div style={{ ...s.card, marginBottom: '24px', padding: '24px', textAlign: 'center' }}>
      <Loading />
    </div>
  )

  if (notFound) return (
    <div style={{ ...s.card, marginBottom: '24px', padding: '20px', borderColor: '#2e2e4e' }}>
      <div style={{ fontSize: '13px', color: '#6b7280' }}>Connection not found — showing all connections below.</div>
    </div>
  )

  if (!connection) return null

  const edgeColor = EDGE_COLORS[connection.connection_type] || EDGE_COLORS.default

  return (
    <div style={{ marginBottom: '28px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: edgeColor, boxShadow: `0 0 8px ${edgeColor}` }} />
          <span style={{ fontSize: '12px', fontWeight: '700', color: '#c4bef8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            AI-Discovered Connection
          </span>
        </div>
        <button
          style={{ ...s.btnGhost, fontSize: '11px', padding: '3px 10px' }}
          onClick={onClear}
        >
          ✕ Clear focus
        </button>
      </div>

      {/* Connection card */}
      <div style={{ ...s.card, borderColor: edgeColor, padding: '20px', position: 'relative', overflow: 'hidden' }}>
        {/* Subtle background glow */}
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '2px', background: edgeColor, opacity: 0.6 }} />

        {/* Papers */}
        <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start', marginBottom: '16px', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: '200px' }}>
            <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Paper A</div>
            <Link to={`/papers/${connection.paper_a_id}`} style={{ ...s.paperLink, fontSize: '13px', fontWeight: '600' }}>
              {connection.paper_a_title || 'Unknown'}
            </Link>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: '20px', gap: '4px', flexShrink: 0 }}>
            <span style={{ width: '28px', height: '2px', background: edgeColor, display: 'block' }} />
            <TypeTag type={connection.connection_type} />
            <span style={{ width: '28px', height: '2px', background: edgeColor, display: 'block' }} />
          </div>

          <div style={{ flex: 1, minWidth: '200px' }}>
            <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Paper B</div>
            <Link to={`/papers/${connection.paper_b_id}`} style={{ ...s.paperLink, fontSize: '13px', fontWeight: '600' }}>
              {connection.paper_b_title || 'Unknown'}
            </Link>
          </div>
        </div>

        {/* Description */}
        {connection.description && (
          <p style={{ fontSize: '13px', color: '#a0a0b8', margin: '0 0 16px', lineHeight: '1.6' }}>
            {connection.description}
          </p>
        )}

        {/* Strength + mini graph */}
        <StrengthBar confidence={connection.confidence} novelty={connection.novelty_score} />

        <div style={{ marginTop: '16px' }}>
          <ConnectionGraph connection={connection} />
        </div>

        {/* Action links */}
        <div style={{ display: 'flex', gap: '12px', marginTop: '16px', flexWrap: 'wrap' }}>
          <Link to={`/papers/${connection.paper_a_id}`} style={{ ...s.btnOutline, fontSize: '12px', padding: '6px 14px' }}>
            View Paper A →
          </Link>
          <Link to={`/papers/${connection.paper_b_id}`} style={{ ...s.btnOutline, fontSize: '12px', padding: '6px 14px' }}>
            View Paper B →
          </Link>
          <Link to={`/explore?paper=${connection.paper_a_id}`} style={{ ...s.btnGhost, fontSize: '12px', padding: '6px 14px' }}>
            Explore in graph ⬡
          </Link>
        </div>
      </div>
    </div>
  )
}

export default function ConnectionsPage() {
  const isMobile = useIsMobile()
  const [searchParams, setSearchParams] = useSearchParams()
  const focusConnectionId = searchParams.get('c')

  const [connections, setConnections] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [typeFilter, setTypeFilter] = useState('')
  const [minConf, setMinConf] = useState(0.5)

  const clearFocus = useCallback(() => {
    setSearchParams({})
  }, [setSearchParams])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: 100, min_confidence: minConf })
      if (typeFilter) params.set('connection_type', typeFilter)
      const data = await fetch(`${API}/connections?${params}`).then(r => r.json())
      setConnections(data.connections || [])
      setTotal(data.total || 0)
    } catch {
      setError('Cannot load connections.')
    }
    setLoading(false)
  }, [typeFilter, minConf])

  useEffect(() => { load() }, [load])

  return (
    <div style={isMobile ? { display: 'flex', flexDirection: 'column' } : s.twoCol}>
      <SEO
        title="Cross-Paper Connections"
        description="Explore connections between research papers discovered through shared scientific content — entities, mechanisms, and findings that link work across disciplines and fields."
        path="/connections"
      />
      <aside style={isMobile ? { padding: '16px', borderBottom: '1px solid #1e1e2e', background: '#0d0d18' } : s.sidebar}>
        <div style={s.sectionTitle}>Filter</div>
        <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '6px' }}>Connection Type</div>
        <select style={{ ...s.input, cursor: 'pointer' }} value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
          <option value="">All types</option>
          {CONNECTION_TYPES.map(t => (
            <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
          ))}
        </select>
        <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '6px' }}>
          Min Confidence: {(minConf * 100).toFixed(0)}%
        </div>
        <input
          type="range" min="0" max="1" step="0.05"
          value={minConf}
          onChange={e => setMinConf(parseFloat(e.target.value))}
          style={{ width: '100%', marginBottom: '16px', cursor: 'pointer' }}
        />
        <div style={{ fontSize: '12px', color: '#6b7280' }}>Showing {connections.length} of {total}</div>
      </aside>
      <main style={isMobile ? { padding: '16px' } : s.content}>
        {error && <ErrorMsg msg={error} />}

        {/* Focused connection panel — shown when ?c=<uuid> is present */}
        {focusConnectionId && (
          <FocusedConnectionPanel
            connectionId={focusConnectionId}
            onClear={clearFocus}
          />
        )}

        {/* All connections list */}
        {loading && <Loading />}
        {!loading && connections.map((c, i) => (
          <div
            key={c.id || i}
            style={{
              ...s.card,
              ...(focusConnectionId && c.id === focusConnectionId
                ? { borderColor: EDGE_COLORS[c.connection_type] || '#7c6af7', opacity: 1 }
                : focusConnectionId
                ? { opacity: 0.5 }
                : {}),
            }}
          >
            <div style={s.connArrow}>
              <Link to={`/papers/${c.paper_a_id}`} style={s.paperLink}>{c.paper_a_title || 'Unknown paper'}</Link>
              <span style={{ fontSize: '12px', color: '#6b7280', paddingTop: '2px', flexShrink: 0 }}>→</span>
              <TypeTag type={c.connection_type} />
              <span style={{ fontSize: '12px', color: '#6b7280', paddingTop: '2px', flexShrink: 0 }}>→</span>
              <Link to={`/papers/${c.paper_b_id}`} style={s.paperLink}>{c.paper_b_title || 'Unknown paper'}</Link>
            </div>
            {c.description && (
              <p style={{ fontSize: '13px', color: '#a0a0b8', marginTop: '8px', lineHeight: '1.6' }}>{c.description}</p>
            )}
            <StrengthBar confidence={c.confidence} novelty={c.novelty_score} />
          </div>
        ))}
      </main>
    </div>
  )
}

import React, { useState, useEffect, useCallback, useRef, Suspense } from 'react'
import { useNavigate } from 'react-router-dom'
import { API, s } from '../shared.js'
import { Loading, ErrorMsg } from '../components/ui.jsx'

// Lazy load the heavy graph component
const ForceGraph2D = React.lazy(() => import('react-force-graph-2d'))

// Discipline-to-color mapping (by source)
const DISCIPLINE_COLORS = {
  pubmed: '#7c6af7',
  biorxiv: '#10b981',
  medrxiv: '#f59e0b',
  arxiv: '#60a5fa',
  crossref: '#a78bfa',
  default: '#94a3b8',
}

// Connection type colors
const EDGE_COLORS = {
  contradicts: '#f43f5e',
  extends: '#10b981',
  mechanism_for: '#3b82f6',
  shares_target: '#c084fc',
  methodological_parallel: '#94a3b8',
  convergent_evidence: '#f59e0b',
  default: '#4b5563',
}

function getDisciplineColor(node) {
  return DISCIPLINE_COLORS[node.source] || DISCIPLINE_COLORS.default
}

function getEdgeColor(link) {
  return EDGE_COLORS[link.type] || EDGE_COLORS.default
}

const LEGEND_ITEMS = [
  { label: 'PubMed', color: DISCIPLINE_COLORS.pubmed },
  { label: 'bioRxiv', color: DISCIPLINE_COLORS.biorxiv },
  { label: 'medRxiv', color: DISCIPLINE_COLORS.medrxiv },
  { label: 'arXiv', color: DISCIPLINE_COLORS.arxiv },
  { label: 'CrossRef', color: DISCIPLINE_COLORS.crossref },
  { label: 'Other', color: DISCIPLINE_COLORS.default },
]

const EDGE_LEGEND = [
  { label: 'Contradicts', color: EDGE_COLORS.contradicts },
  { label: 'Extends', color: EDGE_COLORS.extends },
  { label: 'Mechanism', color: EDGE_COLORS.mechanism_for },
  { label: 'Shares Target', color: EDGE_COLORS.shares_target },
  { label: 'Convergent', color: EDGE_COLORS.convergent_evidence },
  { label: 'Methodological', color: EDGE_COLORS.methodological_parallel },
]

export default function ExplorePage() {
  const navigate = useNavigate()
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [hoveredNode, setHoveredNode] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)
  const [filters, setFilters] = useState({
    disciplines: [],
    connectionTypes: [],
    minConfidence: 0,
  })
  const [legendOpen, setLegendOpen] = useState(true)
  const [filterOpen, setFilterOpen] = useState(true)
  const graphRef = useRef(null)

  const loadGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetch(`${API}/v1/graph/overview?limit=200`).then(r => r.json())
      setGraphData({
        nodes: data.nodes || [],
        links: data.links || [],
      })
    } catch {
      setError('Cannot load graph data.')
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadGraph() }, [loadGraph])

  // Filter graph data
  const filteredData = React.useMemo(() => {
    let nodes = graphData.nodes
    let links = graphData.links

    if (filters.disciplines.length > 0) {
      const discSet = new Set(filters.disciplines)
      nodes = nodes.filter(n => discSet.has(n.source) || discSet.has('other'))
    }

    if (filters.connectionTypes.length > 0) {
      const typeSet = new Set(filters.connectionTypes)
      links = links.filter(l => typeSet.has(l.type))
    }

    if (filters.minConfidence > 0) {
      links = links.filter(l => (l.confidence || 0) >= filters.minConfidence)
    }

    // Only include nodes that have at least one link
    if (links.length < graphData.links.length) {
      const linkedNodeIds = new Set()
      links.forEach(l => {
        linkedNodeIds.add(typeof l.source === 'object' ? l.source.id : l.source)
        linkedNodeIds.add(typeof l.target === 'object' ? l.target.id : l.target)
      })
      nodes = nodes.filter(n => linkedNodeIds.has(n.id))
    }

    return { nodes, links }
  }, [graphData, filters])

  const handleNodeClick = useCallback((node) => {
    setSelectedNode(node)
    navigate(`/papers/${node.id}`)
  }, [navigate])

  const handleNodeHover = useCallback((node) => {
    setHoveredNode(node || null)
  }, [])

  const toggleDiscipline = (disc) => {
    setFilters(f => ({
      ...f,
      disciplines: f.disciplines.includes(disc)
        ? f.disciplines.filter(d => d !== disc)
        : [...f.disciplines, disc],
    }))
  }

  const toggleConnectionType = (type) => {
    setFilters(f => ({
      ...f,
      connectionTypes: f.connectionTypes.includes(type)
        ? f.connectionTypes.filter(t => t !== type)
        : [...f.connectionTypes, type],
    }))
  }

  const dimensions = { width: window.innerWidth - (filterOpen ? 260 : 0), height: window.innerHeight - 57 }

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 57px)', overflow: 'hidden', position: 'relative' }}>
      {/* Filter panel */}
      <aside style={{
        width: filterOpen ? '240px' : '0',
        overflow: 'hidden',
        transition: 'width 0.2s',
        borderRight: '1px solid #1e1e2e',
        background: '#0d0d18',
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
      }}>
        <div style={{ padding: '16px', overflowY: 'auto', flex: 1 }}>
          <div style={{ ...s.sectionTitle, marginBottom: '12px' }}>Filters</div>

          <div style={{ fontSize: '11px', color: '#6b7280', marginBottom: '8px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Source</div>
          {Object.entries(DISCIPLINE_COLORS).filter(([k]) => k !== 'default').map(([key, color]) => (
            <label key={key} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={filters.disciplines.includes(key)}
                onChange={() => toggleDiscipline(key)}
                style={{ accentColor: color }}
              />
              <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: color, flexShrink: 0 }} />
              <span style={{ fontSize: '12px', color: '#9991d0', textTransform: 'capitalize' }}>{key}</span>
            </label>
          ))}

          <div style={{ fontSize: '11px', color: '#6b7280', marginBottom: '8px', marginTop: '16px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Connection Type</div>
          {Object.entries(EDGE_COLORS).filter(([k]) => k !== 'default').map(([key, color]) => (
            <label key={key} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={filters.connectionTypes.includes(key)}
                onChange={() => toggleConnectionType(key)}
                style={{ accentColor: color }}
              />
              <span style={{ width: '10px', height: '4px', background: color, flexShrink: 0, borderRadius: '2px' }} />
              <span style={{ fontSize: '12px', color: '#9991d0' }}>{key.replace(/_/g, ' ')}</span>
            </label>
          ))}

          <div style={{ fontSize: '11px', color: '#6b7280', marginBottom: '6px', marginTop: '16px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Min Confidence: {filters.minConfidence > 0 ? `${(filters.minConfidence * 100).toFixed(0)}%` : 'Any'}
          </div>
          <input
            type="range" min="0" max="1" step="0.05"
            value={filters.minConfidence}
            onChange={e => setFilters(f => ({ ...f, minConfidence: parseFloat(e.target.value) }))}
            style={{ width: '100%', cursor: 'pointer' }}
          />

          <button
            style={{ ...s.btnGhost, width: '100%', marginTop: '16px', fontSize: '12px', padding: '6px' }}
            onClick={() => setFilters({ disciplines: [], connectionTypes: [], minConfidence: 0 })}
          >
            Clear Filters
          </button>

          <div style={{ marginTop: '16px', fontSize: '12px', color: '#6b7280' }}>
            {filteredData.nodes.length} nodes · {filteredData.links.length} edges
          </div>
        </div>
      </aside>

      {/* Toggle filter panel button */}
      <button
        style={{
          position: 'absolute',
          left: filterOpen ? '240px' : '0',
          top: '50%',
          transform: 'translateY(-50%)',
          zIndex: 10,
          background: '#1e1e2e',
          border: '1px solid #2e2e4e',
          borderRadius: '0 6px 6px 0',
          color: '#7c6af7',
          padding: '8px 4px',
          cursor: 'pointer',
          fontSize: '12px',
          transition: 'left 0.2s',
        }}
        onClick={() => setFilterOpen(o => !o)}
      >
        {filterOpen ? '◀' : '▶'}
      </button>

      {/* Graph area */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        {loading && (
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', zIndex: 5 }}>
            <Loading />
          </div>
        )}
        {error && (
          <div style={{ position: 'absolute', top: '20px', left: '50%', transform: 'translateX(-50%)', zIndex: 5 }}>
            <ErrorMsg msg={error} />
          </div>
        )}

        {!loading && filteredData.nodes.length > 0 && (
          <Suspense fallback={<div style={{ padding: '40px', color: '#6b7280' }}>Loading graph engine…</div>}>
            <ForceGraph2D
              ref={graphRef}
              graphData={filteredData}
              width={dimensions.width}
              height={dimensions.height}
              backgroundColor="#0a0a0f"
              nodeColor={getDisciplineColor}
              nodeVal={n => n.val || 3}
              nodeLabel={n => n.title || n.label || n.id}
              linkColor={l => getEdgeColor(l)}
              linkWidth={l => Math.max(0.5, (l.confidence || 0.5) * 2)}
              linkDirectionalParticles={2}
              linkDirectionalParticleWidth={l => (l.confidence || 0) * 2}
              linkDirectionalParticleColor={l => getEdgeColor(l)}
              onNodeClick={handleNodeClick}
              onNodeHover={handleNodeHover}
              nodeCanvasObjectMode={() => 'after'}
              nodeCanvasObject={(node, ctx, globalScale) => {
                if (globalScale < 2) return
                const label = (node.label || '').substring(0, 30)
                const fontSize = 10 / globalScale
                ctx.font = `${fontSize}px Sans-Serif`
                ctx.fillStyle = 'rgba(200, 200, 220, 0.85)'
                ctx.textAlign = 'center'
                ctx.fillText(label, node.x, node.y + (node.val || 3) + fontSize)
              }}
              cooldownTicks={100}
              onEngineStop={() => {
                if (graphRef.current) graphRef.current.zoomToFit(400, 40)
              }}
            />
          </Suspense>
        )}

        {!loading && filteredData.nodes.length === 0 && !error && (
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', color: '#6b7280', textAlign: 'center' }}>
            <div style={{ fontSize: '32px', marginBottom: '12px' }}>⬡</div>
            <div>No graph data matches current filters.</div>
          </div>
        )}

        {/* Hover tooltip */}
        {hoveredNode && (
          <div style={{
            position: 'absolute',
            bottom: '80px',
            left: '50%',
            transform: 'translateX(-50%)',
            background: '#12121e',
            border: '1px solid #1e1e2e',
            borderRadius: '8px',
            padding: '10px 16px',
            maxWidth: '400px',
            zIndex: 20,
            pointerEvents: 'none',
          }}>
            <div style={{ fontSize: '13px', fontWeight: '600', color: '#c4bef8', marginBottom: '4px' }}>{hoveredNode.title}</div>
            <div style={{ fontSize: '11px', color: '#6b7280' }}>
              {hoveredNode.journal && <span>{hoveredNode.journal} · </span>}
              <span style={{ textTransform: 'capitalize' }}>{hoveredNode.source}</span>
              {hoveredNode.val && <span> · {hoveredNode.val} connections</span>}
            </div>
            <div style={{ fontSize: '11px', color: '#7c6af7', marginTop: '4px' }}>Click to view paper →</div>
          </div>
        )}
      </div>

      {/* Legend (bottom-left of graph area) */}
      <div style={{
        position: 'absolute',
        bottom: '16px',
        left: filterOpen ? '256px' : '16px',
        transition: 'left 0.2s',
        background: 'rgba(13, 13, 24, 0.9)',
        border: '1px solid #1e1e2e',
        borderRadius: '8px',
        padding: legendOpen ? '12px' : '8px',
        zIndex: 20,
        minWidth: '140px',
      }}>
        <div
          style={{ fontSize: '11px', color: '#7c6af7', fontWeight: '600', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
          onClick={() => setLegendOpen(o => !o)}
        >
          <span>LEGEND</span>
          <span>{legendOpen ? '−' : '+'}</span>
        </div>
        {legendOpen && (
          <>
            <div style={{ marginTop: '8px' }}>
              <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '4px' }}>Nodes (Source)</div>
              {LEGEND_ITEMS.map(item => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: item.color, flexShrink: 0 }} />
                  <span style={{ fontSize: '11px', color: '#9991d0' }}>{item.label}</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop: '8px' }}>
              <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '4px' }}>Edges (Type)</div>
              {EDGE_LEGEND.map(item => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px' }}>
                  <span style={{ width: '14px', height: '3px', background: item.color, flexShrink: 0, borderRadius: '2px' }} />
                  <span style={{ fontSize: '11px', color: '#9991d0' }}>{item.label}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'

export default function Connections() {
  const [connections, setConnections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.connections({ limit: 100 })
      .then(d => {
        setConnections(d.connections || d || [])
        setLoading(false)
      })
      .catch(() => {
        setError('Failed to load connections.')
        setLoading(false)
      })
  }, [])

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '80px 0', color: '#6b7280', fontSize: 14 }}>Loading connections…</div>
  }

  if (error) {
    return <div style={{ textAlign: 'center', padding: '80px 0', color: '#f87171', fontSize: 14 }}>{error}</div>
  }

  return (
    <div>
      <div className="mb-6">
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: '0 0 4px', color: '#e0e0e8' }}>Connections</h1>
        <p style={{ fontSize: 13, color: '#6b7280', margin: 0 }}>
          {connections.length} AI-discovered connections between concepts across papers
        </p>
      </div>

      {connections.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#6b7280', fontSize: 14 }}>
          No connections found yet. The pipeline is still running.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {connections.map((c, i) => {
            const confidence = c.confidence != null ? (c.confidence * 100).toFixed(0) : null
            const strengthColor = confidence >= 80 ? '#4ade80' : confidence >= 50 ? '#fbbf24' : '#9ca3af'

            return (
              <div
                key={c.id || i}
                style={{
                  background: '#12121e',
                  border: '1px solid #1e1e2e',
                  borderRadius: 8,
                  padding: '14px 16px',
                }}
              >
                {/* Connection header */}
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span style={{ fontSize: 14, fontWeight: 600, color: '#9991d0' }}>
                    {c.entity_a || c.source_concept || c.concept_a || '?'}
                  </span>
                  <span style={{ fontSize: 13, color: '#6b7280', background: '#1e1e2e', borderRadius: 4, padding: '1px 8px' }}>
                    {c.connection_type || c.relationship_type || 'relates to'}
                  </span>
                  <span style={{ fontSize: 14, fontWeight: 600, color: '#9991d0' }}>
                    {c.entity_b || c.target_concept || c.concept_b || '?'}
                  </span>
                  {confidence && (
                    <span style={{ marginLeft: 'auto', fontSize: 12, color: strengthColor, fontWeight: 600 }}>
                      {confidence}% confidence
                    </span>
                  )}
                </div>

                {/* Description */}
                {c.description && (
                  <p style={{ fontSize: 13, color: '#8b8ba8', lineHeight: 1.5, margin: '0 0 8px' }}>
                    {c.description}
                  </p>
                )}

                {/* Source/target papers */}
                <div className="flex flex-wrap gap-3" style={{ fontSize: 12, color: '#6b7280' }}>
                  {c.source_paper_id && (
                    <Link to={`/paper/${c.source_paper_id}`} style={{ color: '#7c6af7' }}>
                      Source paper →
                    </Link>
                  )}
                  {c.target_paper_id && c.target_paper_id !== c.source_paper_id && (
                    <Link to={`/paper/${c.target_paper_id}`} style={{ color: '#7c6af7' }}>
                      Target paper →
                    </Link>
                  )}
                  {c.paper_id && !c.source_paper_id && (
                    <Link to={`/paper/${c.paper_id}`} style={{ color: '#7c6af7' }}>
                      View paper →
                    </Link>
                  )}
                  {c.source_paper_title && (
                    <span style={{ color: '#6b7280' }}>{c.source_paper_title?.slice(0, 60)}{c.source_paper_title?.length > 60 ? '…' : ''}</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

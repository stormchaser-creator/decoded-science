import React, { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api } from '../api.js'

function StatCard({ value, label, color = '#7c6af7' }) {
  return (
    <div style={{
      background: '#12121e',
      border: '1px solid #1e1e2e',
      borderRadius: 10,
      padding: '20px',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 36, fontWeight: 700, color }}>{value ?? '—'}</div>
      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.8px' }}>{label}</div>
    </div>
  )
}

export default function Home() {
  const [stats, setStats] = useState(null)
  const [q, setQ] = useState('')
  const [recentPapers, setRecentPapers] = useState([])
  const navigate = useNavigate()

  useEffect(() => {
    api.stats().then(setStats).catch(() => {})
    api.papers({ limit: 5, order_by: 'date' }).then(d => setRecentPapers(d.papers || [])).catch(() => {})
  }, [])

  function handleSearch(e) {
    e.preventDefault()
    if (q.trim()) navigate(`/search?q=${encodeURIComponent(q.trim())}`)
  }

  const total = stats?.papers?.total?.toLocaleString() ?? '…'
  const extracted = stats?.papers?.by_status?.extracted?.toLocaleString() ?? '…'
  const connections = stats?.connections?.total?.toLocaleString() ?? '…'
  const critiques = stats?.critiques?.total?.toLocaleString() ?? '…'

  return (
    <div>
      {/* Hero */}
      <div className="text-center py-12 sm:py-16">
        <div style={{ fontSize: 48, marginBottom: 12, lineHeight: 1 }}>⬡</div>
        <h1 style={{ fontSize: 'clamp(28px, 5vw, 48px)', fontWeight: 800, marginBottom: 12, color: '#e0e0e8', lineHeight: 1.15 }}>
          Literature Connectome
        </h1>
        <p style={{ fontSize: 16, color: '#6b7280', maxWidth: 520, margin: '0 auto 32px' }}>
          AI-extracted connections across {total} scientific papers.
          Discover hidden bridges between research domains.
        </p>

        {/* Search bar */}
        <form onSubmit={handleSearch} className="flex gap-3 max-w-xl mx-auto mb-8">
          <input
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Search: IL-6, sleep deprivation, neuroinflammation…"
            style={{
              flex: 1,
              background: '#12121e',
              border: '1px solid #2a2a3e',
              borderRadius: 10,
              padding: '14px 18px',
              fontSize: 15,
              color: '#e0e0e8',
              outline: 'none',
            }}
          />
          <button
            type="submit"
            style={{
              background: '#7c6af7',
              color: '#fff',
              border: 'none',
              borderRadius: 10,
              padding: '14px 24px',
              fontSize: 15,
              fontWeight: 600,
              cursor: 'pointer',
              flexShrink: 0,
            }}
          >
            Search
          </button>
        </form>

        {/* CTA buttons */}
        <div className="flex flex-wrap gap-3 justify-center">
          <Link to="/papers">
            <button style={{
              background: '#12121e',
              color: '#e0e0e8',
              border: '1px solid #1e1e2e',
              borderRadius: 8,
              padding: '10px 22px',
              fontSize: 14,
              cursor: 'pointer',
              fontWeight: 500,
            }}>
              Browse Papers →
            </button>
          </Link>
          <Link to="/bridge">
            <button style={{
              background: 'rgba(124,106,247,0.12)',
              color: '#7c6af7',
              border: '1px solid rgba(124,106,247,0.3)',
              borderRadius: 8,
              padding: '10px 22px',
              fontSize: 14,
              cursor: 'pointer',
              fontWeight: 500,
            }}>
              Find a Bridge ⬡
            </button>
          </Link>
          <Link to="/connections">
            <button style={{
              background: '#12121e',
              color: '#e0e0e8',
              border: '1px solid #1e1e2e',
              borderRadius: 8,
              padding: '10px 22px',
              fontSize: 14,
              cursor: 'pointer',
              fontWeight: 500,
            }}>
              View Connections
            </button>
          </Link>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-12">
        <StatCard value={total} label="Total Papers" color="#7c6af7" />
        <StatCard value={extracted} label="AI-Extracted" color="#4ade80" />
        <StatCard value={connections} label="Connections Found" color="#fbbf24" />
        <StatCard value={critiques} label="Intel Briefs" color="#60a5fa" />
      </div>

      {/* Recent papers */}
      {recentPapers.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 style={{ fontSize: 16, fontWeight: 600, color: '#9991d0', textTransform: 'uppercase', letterSpacing: '0.8px', margin: 0 }}>
              Recent Papers
            </h2>
            <Link to="/papers" style={{ fontSize: 13, color: '#7c6af7' }}>View all →</Link>
          </div>
          <div className="grid gap-3">
            {recentPapers.map(p => (
              <Link key={p.id} to={`/paper/${p.id}`}>
                <div style={{
                  background: '#12121e',
                  border: '1px solid #1e1e2e',
                  borderRadius: 8,
                  padding: '14px 16px',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s',
                }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = '#7c6af7'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = '#1e1e2e'}
                >
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#e0e0e8', marginBottom: 6, lineHeight: 1.4 }}>
                    {p.title}
                  </div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>
                    {p.journal && <span>{p.journal}</span>}
                    {p.journal && p.published_date && <span> · </span>}
                    {p.published_date && <span>{String(p.published_date).slice(0, 4)}</span>}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

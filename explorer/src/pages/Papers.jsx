import React, { useEffect, useState, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api.js'

function PaperCard({ paper }) {
  const year = paper.published_date ? String(paper.published_date).slice(0, 4) : null
  const statusColor = paper.status === 'extracted' || paper.status === 'connected' ? '#4ade80' : '#9ca3af'

  return (
    <Link to={`/paper/${paper.id}`}>
      <div
        style={{
          background: '#12121e',
          border: '1px solid #1e1e2e',
          borderRadius: 8,
          padding: '16px',
          marginBottom: 8,
          cursor: 'pointer',
          transition: 'border-color 0.15s',
        }}
        onMouseEnter={e => e.currentTarget.style.borderColor = '#7c6af7'}
        onMouseLeave={e => e.currentTarget.style.borderColor = '#1e1e2e'}
      >
        <div style={{ fontSize: 14, fontWeight: 600, color: '#e0e0e8', marginBottom: 6, lineHeight: 1.45 }}>
          {paper.title}
        </div>
        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
          {paper.journal && <span>{paper.journal}</span>}
          {paper.journal && year && <span> · </span>}
          {year && <span>{year}</span>}
        </div>
        {paper.abstract && (
          <p style={{ fontSize: 12, color: '#8b8ba8', lineHeight: 1.6, margin: '0 0 10px', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {paper.abstract}
          </p>
        )}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-block', background: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.2)', borderRadius: 4, padding: '2px 8px', fontSize: 11, color: statusColor }}>
            {paper.status}
          </span>
          {paper.connection_count > 0 && (
            <span style={{ display: 'inline-block', background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.2)', borderRadius: 4, padding: '2px 8px', fontSize: 11, color: '#fbbf24' }}>
              {paper.connection_count} connections
            </span>
          )}
          {paper.doi && (
            <span style={{ display: 'inline-block', background: '#1e1e2e', borderRadius: 4, padding: '2px 8px', fontSize: 11, color: '#9991d0' }}>
              DOI
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}

export default function Papers() {
  const [papers, setPapers] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  const perPage = 20

  const load = useCallback(async (pageNum = 0, searchQ = '') => {
    setLoading(true)
    setError(null)
    try {
      if (searchQ) {
        const data = await api.search(searchQ, perPage)
        setPapers(data.results || [])
        setTotal(data.results?.length || 0)
      } else {
        const data = await api.papers({ limit: perPage, offset: pageNum * perPage })
        setPapers(data.papers || [])
        setTotal(data.total || 0)
      }
    } catch (e) {
      setError('Failed to load papers. Is the API running?')
    }
    setLoading(false)
  }, [])

  useEffect(() => { load(0, '') }, [load])

  function handleSearch(e) {
    e.preventDefault()
    setPage(0)
    if (q.trim()) {
      navigate(`/search?q=${encodeURIComponent(q.trim())}`)
    } else {
      load(0, '')
    }
  }

  function goPage(n) {
    setPage(n)
    load(n, '')
    window.scrollTo(0, 0)
  }

  const totalPages = Math.ceil(total / perPage)

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: '#e0e0e8' }}>Papers</h1>
          {total > 0 && <p style={{ fontSize: 13, color: '#6b7280', margin: '4px 0 0' }}>{total.toLocaleString()} papers in the database</p>}
        </div>
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Search within papers…"
            style={{
              background: '#12121e',
              border: '1px solid #1e1e2e',
              borderRadius: 8,
              padding: '9px 14px',
              fontSize: 13,
              color: '#e0e0e8',
              outline: 'none',
              width: 220,
            }}
          />
          <button
            type="submit"
            style={{
              background: '#7c6af7',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              padding: '9px 18px',
              fontSize: 13,
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            Search
          </button>
        </form>
      </div>

      {error && (
        <div style={{ background: '#1a0808', border: '1px solid #4a1010', borderRadius: 8, padding: '12px 16px', color: '#f87171', fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#6b7280', fontSize: 14 }}>
          Loading papers…
        </div>
      ) : papers.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#6b7280', fontSize: 14 }}>
          No papers found.
        </div>
      ) : (
        <>
          {papers.map(p => <PaperCard key={p.id} paper={p} />)}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-8">
              <button
                onClick={() => goPage(page - 1)}
                disabled={page === 0}
                style={{
                  background: '#12121e',
                  border: '1px solid #1e1e2e',
                  borderRadius: 6,
                  padding: '7px 14px',
                  fontSize: 13,
                  color: page === 0 ? '#4b5563' : '#e0e0e8',
                  cursor: page === 0 ? 'not-allowed' : 'pointer',
                }}
              >
                ← Prev
              </button>
              <span style={{ fontSize: 13, color: '#6b7280', padding: '0 8px' }}>
                Page {page + 1} of {totalPages}
              </span>
              <button
                onClick={() => goPage(page + 1)}
                disabled={page >= totalPages - 1}
                style={{
                  background: '#12121e',
                  border: '1px solid #1e1e2e',
                  borderRadius: 6,
                  padding: '7px 14px',
                  fontSize: 13,
                  color: page >= totalPages - 1 ? '#4b5563' : '#e0e0e8',
                  cursor: page >= totalPages - 1 ? 'not-allowed' : 'pointer',
                }}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

import React, { useEffect, useState } from 'react'
import { useSearchParams, Link, useNavigate } from 'react-router-dom'
import { api } from '../api.js'

export default function Search() {
  const [searchParams] = useSearchParams()
  const q = searchParams.get('q') || ''
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [inputQ, setInputQ] = useState(q)
  const navigate = useNavigate()

  useEffect(() => {
    setInputQ(q)
    if (!q) return
    setLoading(true)
    setError(null)
    api.search(q, 30)
      .then(data => {
        setResults(data.results || [])
        setLoading(false)
      })
      .catch(() => {
        setError('Search failed. Is the API running?')
        setLoading(false)
      })
  }, [q])

  function handleSearch(e) {
    e.preventDefault()
    if (inputQ.trim()) navigate(`/search?q=${encodeURIComponent(inputQ.trim())}`)
  }

  return (
    <div>
      <div className="mb-6">
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: '0 0 16px', color: '#e0e0e8' }}>Search</h1>
        <form onSubmit={handleSearch} className="flex gap-3 max-w-xl">
          <input
            value={inputQ}
            onChange={e => setInputQ(e.target.value)}
            placeholder="Search papers by keyword, author, or concept…"
            style={{
              flex: 1,
              background: '#12121e',
              border: '1px solid #2a2a3e',
              borderRadius: 8,
              padding: '11px 14px',
              fontSize: 14,
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
              borderRadius: 8,
              padding: '11px 20px',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              flexShrink: 0,
            }}
          >
            Search
          </button>
        </form>
      </div>

      {q && (
        <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
          {loading ? 'Searching…' : `${results.length} results for "${q}"`}
        </div>
      )}

      {error && (
        <div style={{ background: '#1a0808', border: '1px solid #4a1010', borderRadius: 8, padding: '12px 16px', color: '#f87171', fontSize: 13, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!q && !loading && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#6b7280', fontSize: 14 }}>
          Enter a search term above to find papers.
        </div>
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#6b7280', fontSize: 14 }}>
          Searching…
        </div>
      )}

      {!loading && results.length === 0 && q && !error && (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <div style={{ fontSize: 14, color: '#6b7280', marginBottom: 12 }}>No results found for "{q}"</div>
          <Link to="/papers" style={{ fontSize: 13, color: '#7c6af7' }}>Browse all papers →</Link>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {results.map((r, i) => {
          const paper = r.paper || r
          const score = r.score ?? r.relevance ?? null
          const year = paper.published_date ? String(paper.published_date).slice(0, 4) : null

          return (
            <Link key={paper.id || i} to={`/paper/${paper.id}`}>
              <div
                style={{
                  background: '#12121e',
                  border: '1px solid #1e1e2e',
                  borderRadius: 8,
                  padding: '16px',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = '#7c6af7'}
                onMouseLeave={e => e.currentTarget.style.borderColor = '#1e1e2e'}
              >
                <div className="flex items-start justify-between gap-4 mb-2">
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#e0e0e8', lineHeight: 1.4 }}>
                    {paper.title}
                  </div>
                  {score != null && (
                    <div style={{ flexShrink: 0, fontSize: 12, color: '#7c6af7', fontWeight: 600, background: 'rgba(124,106,247,0.1)', borderRadius: 4, padding: '2px 8px' }}>
                      {typeof score === 'number' ? score.toFixed(3) : score}
                    </div>
                  )}
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>
                  {paper.journal && <span>{paper.journal}</span>}
                  {paper.journal && year && <span> · </span>}
                  {year && <span>{year}</span>}
                </div>
                {paper.abstract && (
                  <p style={{
                    fontSize: 12,
                    color: '#8b8ba8',
                    lineHeight: 1.6,
                    margin: 0,
                    display: '-webkit-box',
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                  }}>
                    {paper.abstract}
                  </p>
                )}
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}

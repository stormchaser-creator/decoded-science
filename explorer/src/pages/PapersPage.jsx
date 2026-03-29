import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { API, s, useIsMobile } from '../shared.js'
import { ErrorMsg } from '../components/ui.jsx'

const PAGE_SIZE = 50

export default function PapersPage() {
  const isMobile = useIsMobile()
  const [papers, setPapers] = useState([])
  const [searchQ, setSearchQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [skip, setSkip] = useState(0)
  const [total, setTotal] = useState(0)
  const [isSearch, setIsSearch] = useState(false)

  const loadPapers = useCallback(async (q = '', offset = 0) => {
    setLoading(true)
    setError(null)
    try {
      let data
      if (q) {
        data = await fetch(`${API}/search?q=${encodeURIComponent(q)}&limit=${PAGE_SIZE}`).then(r => r.json())
        setPapers(data.results || [])
        setTotal(data.count || 0)
        setIsSearch(true)
      } else {
        data = await fetch(`${API}/papers?limit=${PAGE_SIZE}&offset=${offset}&status=extracted`).then(r => r.json())
        setPapers(data.papers || [])
        setTotal(data.total || 0)
        setIsSearch(false)
      }
    } catch {
      setError('Cannot reach Decoded API.')
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadPapers('', skip) }, [skip])

  const handleSearch = () => { setSkip(0); loadPapers(searchQ, 0) }
  const handleClear = () => { setSearchQ(''); setSkip(0); loadPapers('', 0) }

  return (
    <div style={isMobile ? { display: 'flex', flexDirection: 'column' } : s.twoCol}>
      <aside style={isMobile ? { padding: '16px', borderBottom: '1px solid #1e1e2e', background: '#0d0d18' } : s.sidebar}>
        <div style={s.sectionTitle}>Search Papers</div>
        <input
          style={s.input}
          placeholder="e.g. IL-6 inflammation sleep"
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
        />
        <button style={{ ...s.btn, width: '100%' }} onClick={handleSearch}>
          {loading ? 'Searching…' : 'Search'}
        </button>
        <button style={{ ...s.btnGhost, marginTop: '8px', width: '100%' }} onClick={handleClear}>
          Clear / Load All
        </button>
        {!isSearch && total > 0 && (
          <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '16px' }}>
            Showing {skip + 1}–{Math.min(skip + PAGE_SIZE, total)} of {total}
          </div>
        )}
      </aside>
      <main style={isMobile ? { padding: '16px', overflowY: 'auto' } : s.content}>
        {error && <ErrorMsg msg={error} />}
        <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '14px' }}>
          {loading ? 'Loading…' : isSearch ? `${papers.length} results` : `${total} extracted papers`}
        </div>
        {papers.map(p => (
          <Link key={p.id} to={`/papers/${p.id}`} style={{ textDecoration: 'none' }}>
            <div
              style={s.card}
              onMouseEnter={e => e.currentTarget.style.borderColor = '#7c6af7'}
              onMouseLeave={e => e.currentTarget.style.borderColor = '#1e1e2e'}
            >
              <div style={s.paperLink}>{p.title}</div>
              <div style={s.paperMeta}>
                {p.journal && <span>{p.journal} · </span>}
                {p.published_date && <span>{String(p.published_date).slice(0, 4)}</span>}
              </div>
              <div>
                <span style={{ ...s.tag, ...(p.status === 'extracted' || p.status === 'connected' ? s.tagGreen : {}) }}>
                  {p.status}
                </span>
                {p.connection_count > 0 && (
                  <span style={{ ...s.tag, ...s.tagYellow }}>{p.connection_count} connections</span>
                )}
                {p.critique_quality != null && (
                  <span style={{ ...s.tag, ...s.tagBlue }}>quality {p.critique_quality}/10</span>
                )}
              </div>
            </div>
          </Link>
        ))}
        {!isSearch && total > PAGE_SIZE && (
          <div style={s.paginationRow}>
            <button
              style={{ ...s.btnOutline, opacity: skip === 0 ? 0.4 : 1 }}
              disabled={skip === 0}
              onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
            >← Prev</button>
            <span>Page {Math.floor(skip / PAGE_SIZE) + 1} of {Math.ceil(total / PAGE_SIZE)}</span>
            <button
              style={{ ...s.btnOutline, opacity: skip + PAGE_SIZE >= total ? 0.4 : 1 }}
              disabled={skip + PAGE_SIZE >= total}
              onClick={() => setSkip(skip + PAGE_SIZE)}
            >Next →</button>
          </div>
        )}
      </main>
    </div>
  )
}

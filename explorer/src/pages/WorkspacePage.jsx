import React, { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { API, s, authFetch } from '../shared.js'
import { useAuth } from '../auth.jsx'
import { Loading, ErrorMsg } from '../components/ui.jsx'
import SEO from '../components/SEO.jsx'

export default function WorkspacePage() {
  const { user, token } = useAuth()
  const navigate = useNavigate()
  const [searches, setSearches] = useState([])
  const [collections, setCollections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [newSearch, setNewSearch] = useState({ name: '', query: '' })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!user) { navigate('/login'); return }
    Promise.all([
      authFetch(`${API}/workspace/searches`, token).then(r => r.json()),
      authFetch(`${API}/workspace/collections`, token).then(r => r.json()),
    ]).then(([sd, cd]) => {
      setSearches(sd.searches || [])
      setCollections(cd.collections || [])
      setLoading(false)
    }).catch(() => {
      setError('Cannot load workspace.')
      setLoading(false)
    })
  }, [user, token])

  const saveSearch = async e => {
    e.preventDefault()
    if (!newSearch.name || !newSearch.query) return
    setSaving(true)
    try {
      const res = await authFetch(`${API}/workspace/searches`, token, {
        method: 'POST',
        body: JSON.stringify({ name: newSearch.name, query: newSearch.query, filters: {} }),
      })
      if (res.ok) {
        const saved = await res.json()
        setSearches(p => [saved, ...p])
        setNewSearch({ name: '', query: '' })
      }
    } catch {}
    setSaving(false)
  }

  const deleteSearch = async id => {
    try {
      await authFetch(`${API}/workspace/searches/${id}`, token, { method: 'DELETE' })
      setSearches(p => p.filter(item => item.id !== id))
    } catch {}
  }

  if (!user) return null

  return (
    <div style={s.page}>
      <SEO title="Your Workspace" description="Your personal research workspace on The Decoded Human." path="/workspace" noindex={true} />
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#e0e0e8', margin: '0 0 4px' }}>Workspace</h2>
        <div style={{ fontSize: '13px', color: '#6b7280' }}>
          Welcome back, {user.name || user.email}
          {user.role && user.role !== 'user' && (
            <span style={{ ...s.tag, ...s.tagPurple, marginLeft: '8px' }}>{user.role}</span>
          )}
        </div>
      </div>
      {error && <ErrorMsg msg={error} />}
      {loading && <Loading />}
      {!loading && (
        <div style={s.gridTwo}>
          <div>
            <div style={s.sectionTitle}>Saved Searches ({searches.length})</div>
            <div style={s.card}>
              <div style={{ fontSize: '13px', color: '#9991d0', marginBottom: '10px', fontWeight: '600' }}>Save a new search</div>
              <form onSubmit={saveSearch}>
                <input style={s.input} placeholder="Search name (e.g. IL-6 studies)" value={newSearch.name} onChange={e => setNewSearch(p => ({ ...p, name: e.target.value }))} />
                <input style={s.input} placeholder="Query terms" value={newSearch.query} onChange={e => setNewSearch(p => ({ ...p, query: e.target.value }))} />
                <button style={s.btn} type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save search'}</button>
              </form>
            </div>
            <div style={{ marginTop: '12px' }}>
              {searches.length === 0 && (
                <div style={{ fontSize: '13px', color: '#6b7280' }}>No saved searches yet.</div>
              )}
              {searches.map(item => (
                <div key={item.id} style={{ background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '8px', padding: '12px', marginBottom: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '13px', fontWeight: '600', color: '#e0e0e8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</div>
                    <div style={{ fontSize: '12px', color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.query}</div>
                  </div>
                  <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                    <Link to={`/papers?q=${encodeURIComponent(item.query)}`} style={{ background: 'transparent', color: '#7c6af7', border: '1px solid #7c6af7', borderRadius: '4px', padding: '3px 8px', fontSize: '11px', textDecoration: 'none' }}>
                      Run
                    </Link>
                    <button
                      style={{ background: '#1a0808', color: '#f87171', border: '1px solid #4a1010', borderRadius: '4px', padding: '3px 8px', fontSize: '11px', cursor: 'pointer' }}
                      onClick={() => deleteSearch(item.id)}
                    >×</button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div style={s.sectionTitle}>Collections ({collections.length})</div>
            {collections.length === 0 && (
              <div style={{ fontSize: '13px', color: '#6b7280' }}>
                No collections yet. Collections let you group papers by topic or project.
              </div>
            )}
            {collections.map(c => (
              <div key={c.id} style={{ background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '8px', padding: '14px', marginBottom: '8px' }}>
                <div style={{ fontSize: '13px', fontWeight: '600', color: '#e0e0e8' }}>{c.name}</div>
                {c.description && <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>{c.description}</div>}
                <div style={{ fontSize: '11px', color: '#4b4b6b', marginTop: '6px' }}>{c.paper_count || 0} papers</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

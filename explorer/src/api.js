const BASE = '/api'

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  return res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  return res.json()
}

export const api = {
  stats: () => get('/stats'),
  papers: (params = {}) => {
    const q = new URLSearchParams({ limit: 20, offset: 0, ...params })
    return get(`/papers?${q}`)
  },
  paper: (id) => get(`/papers/${id}`),
  paperConnections: (id) => get(`/papers/${id}/connections`),
  paperCritique: (id) => get(`/papers/${id}/critique`),
  connections: (params = {}) => {
    const q = new URLSearchParams({ limit: 50, ...params })
    return get(`/connections?${q}`)
  },
  search: (q, limit = 20) => get(`/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  bridge: (concept_a, concept_b, max_hops = 4) =>
    post('/bridge', { concept_a, concept_b, max_hops }),
}

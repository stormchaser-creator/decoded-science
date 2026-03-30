import { useState, useEffect } from 'react'

export const API = import.meta.env.VITE_API_URL || '/api'

export function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < breakpoint)
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < breakpoint)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [breakpoint])
  return isMobile
}

// Epistemic color system (Step 4)
export const EPISTEMIC = {
  fact: '#3b82f6',         // blue
  interpretation: '#8b5cf6', // purple
  hypothesis: '#f59e0b',   // amber
  convergence: '#10b981',  // green
  contradiction: '#f43f5e', // red
  speculation: '#94a3b8',  // slate
}

export function epistemicColor(evidenceStrength) {
  if (!evidenceStrength) return EPISTEMIC.speculation
  const s = evidenceStrength.toLowerCase()
  if (s.includes('strong') || s.includes('high') || s.includes('direct')) return EPISTEMIC.fact
  if (s.includes('moderate') || s.includes('medium')) return EPISTEMIC.interpretation
  if (s.includes('weak') || s.includes('low') || s.includes('indirect')) return EPISTEMIC.hypothesis
  if (s.includes('convergent') || s.includes('replicate')) return EPISTEMIC.convergence
  if (s.includes('contradict')) return EPISTEMIC.contradiction
  return EPISTEMIC.speculation
}

export function connectionEpistemicColor(connectionType) {
  if (!connectionType) return EPISTEMIC.speculation
  const t = connectionType.toLowerCase()
  if (t === 'contradicts') return EPISTEMIC.contradiction       // red
  if (t === 'extends') return EPISTEMIC.convergence             // green (matches TYPE_COLORS)
  if (t === 'mechanism_for') return EPISTEMIC.fact              // blue
  if (t === 'shares_target') return EPISTEMIC.interpretation    // purple
  if (t === 'convergent_evidence') return EPISTEMIC.hypothesis  // amber
  if (t === 'methodological_parallel') return EPISTEMIC.speculation
  return EPISTEMIC.speculation
}

export const s = {
  app: { minHeight: '100vh', background: '#0a0a0f', color: '#e0e0e8', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  header: { borderBottom: '1px solid #1e1e2e', padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '20px', background: '#0d0d18', position: 'sticky', top: 0, zIndex: 100 },
  logo: { fontSize: '18px', fontWeight: '700', color: '#7c6af7', letterSpacing: '-0.5px', textDecoration: 'none', flexShrink: 0 },
  tagline: { fontSize: '12px', color: '#6b7280', marginTop: '1px' },
  nav: { display: 'flex', gap: '2px', flexWrap: 'wrap' },
  navLink: { padding: '5px 12px', borderRadius: '6px', fontSize: '14px', color: '#9991d0', textDecoration: 'none', transition: 'background 0.15s' },
  navLinkActive: { background: '#1e1e2e', color: '#c4bef8' },
  statsBar: { display: 'flex', gap: '20px', marginLeft: 'auto', fontSize: '13px', color: '#6b7280', flexShrink: 0 },
  page: { padding: '24px', maxWidth: '1100px', margin: '0 auto' },
  sectionTitle: { fontSize: '12px', fontWeight: '600', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '14px' },
  card: { background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '8px', padding: '16px', marginBottom: '10px' },
  paperLink: { fontSize: '15px', fontWeight: '600', color: '#7c6af7', lineHeight: '1.4', textDecoration: 'none' },
  paperMeta: { fontSize: '13px', color: '#6b7280', marginTop: '4px' },
  tag: { display: 'inline-block', background: '#1e1e2e', borderRadius: '4px', padding: '2px 8px', fontSize: '12px', color: '#9991d0', marginRight: '6px', marginTop: '4px' },
  tagGreen: { background: '#0d2010', color: '#4ade80' },
  tagYellow: { background: '#1a1500', color: '#fbbf24' },
  tagRed: { background: '#1a0808', color: '#f87171' },
  tagBlue: { background: '#0a0a20', color: '#60a5fa' },
  tagPurple: { background: '#140a20', color: '#c084fc' },
  input: { width: '100%', background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '6px', padding: '8px 12px', color: '#e0e0e8', fontSize: '14px', outline: 'none', marginBottom: '8px', boxSizing: 'border-box' },
  btn: { background: '#7c6af7', color: '#fff', border: 'none', borderRadius: '6px', padding: '8px 16px', fontSize: '14px', cursor: 'pointer' },
  btnOutline: { background: 'transparent', color: '#7c6af7', border: '1px solid #7c6af7', borderRadius: '6px', padding: '6px 12px', fontSize: '13px', cursor: 'pointer', textDecoration: 'none', display: 'inline-block' },
  btnGhost: { background: '#1e1e2e', color: '#9991d0', border: 'none', borderRadius: '6px', padding: '8px 16px', fontSize: '14px', cursor: 'pointer' },
  errorBanner: { background: '#1a0808', border: '1px solid #4a1010', borderRadius: '8px', padding: '12px', color: '#f87171', fontSize: '14px', marginBottom: '16px' },
  successBanner: { background: '#0d2010', border: '1px solid #1a4020', borderRadius: '8px', padding: '12px', color: '#4ade80', fontSize: '14px', marginBottom: '16px' },
  connArrow: { display: 'flex', alignItems: 'flex-start', gap: '8px', flexWrap: 'wrap' },
  strength: { height: '4px', borderRadius: '2px', background: '#1e1e2e', marginTop: '8px', overflow: 'hidden' },
  strengthBar: { height: '4px', borderRadius: '2px', background: '#7c6af7' },
  twoCol: { display: 'grid', gridTemplateColumns: '260px 1fr', height: 'calc(100vh - 57px)' },
  sidebar: { borderRight: '1px solid #1e1e2e', padding: '20px', overflowY: 'auto', background: '#0d0d18' },
  content: { padding: '24px', overflowY: 'auto' },
  formCard: { background: '#12121e', border: '1px solid #1e1e2e', borderRadius: '10px', padding: '32px', maxWidth: '420px', margin: '60px auto' },
  formTitle: { fontSize: '22px', fontWeight: '700', color: '#e0e0e8', marginBottom: '6px' },
  formSub: { fontSize: '14px', color: '#6b7280', marginBottom: '24px' },
  label: { display: 'block', fontSize: '13px', color: '#9991d0', marginBottom: '4px', fontWeight: '500' },
  paginationRow: { display: 'flex', alignItems: 'center', gap: '8px', padding: '16px 0', fontSize: '14px', color: '#6b7280' },
  bigStat: { fontSize: '28px', fontWeight: '700', color: '#7c6af7' },
  gridTwo: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' },
}

export const TYPE_COLORS = {
  contradicts: s.tagRed,
  extends: s.tagGreen,
  mechanism_for: s.tagBlue,
  shares_target: s.tagPurple,
  methodological_parallel: s.tag,
  convergent_evidence: s.tagYellow,
}

export function authFetch(url, token, opts = {}) {
  return fetch(url, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  })
}

export function parseJsonField(val) {
  if (!val) return []
  if (Array.isArray(val)) return val
  if (typeof val === 'string') {
    try { return JSON.parse(val) } catch { return [] }
  }
  return []
}

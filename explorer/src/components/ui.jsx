import React from 'react'
import { s, TYPE_COLORS } from '../shared.js'

export function TypeTag({ type }) {
  const color = TYPE_COLORS[type] || s.tag
  return <span style={{ ...s.tag, ...color }}>{type?.replace(/_/g, ' ')}</span>
}

export function StrengthBar({ confidence, novelty }) {
  return (
    <div>
      <div style={s.strength}>
        <div style={{ ...s.strengthBar, width: `${(confidence || 0) * 100}%` }} />
      </div>
      <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
        Confidence: {((confidence || 0) * 100).toFixed(0)}%
        {novelty != null && ` · Novelty: ${(novelty * 100).toFixed(0)}%`}
      </div>
    </div>
  )
}

export function Loading() {
  return <div style={{ color: '#6b7280', fontSize: '13px', padding: '32px 0' }}>Loading…</div>
}

export function ErrorMsg({ msg }) {
  return <div style={s.errorBanner}>{msg}</div>
}

export function navLinkStyle({ isActive }) {
  return isActive ? { ...s.navLink, ...s.navLinkActive } : s.navLink
}

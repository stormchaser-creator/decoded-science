import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { API, s } from '../shared.js'
import { useAuth } from '../auth.jsx'
import { ErrorMsg } from '../components/ui.jsx'
import SEO from '../components/SEO.jsx'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const { login } = useAuth()
  const navigate = useNavigate()

  const submit = async e => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Login failed')
      login(data.user, data.token)
      navigate('/workspace')
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }

  return (
    <div style={s.formCard}>
      <SEO title="Sign In" description="Sign in to The Decoded Human to access your workspace, saved analyses, and personalized research tools." path="/login" noindex={true} />
      <div style={s.formTitle}>Sign in</div>
      <div style={s.formSub}>Access your workspace and saved searches.</div>
      {error && <ErrorMsg msg={error} />}
      <form onSubmit={submit}>
        <label style={s.label}>Email</label>
        <input style={s.input} type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} required />
        <label style={s.label}>Password</label>
        <input style={s.input} type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} required />
        <button style={{ ...s.btn, width: '100%', padding: '10px', marginTop: '8px' }} type="submit" disabled={loading}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <div style={{ textAlign: 'center', marginTop: '16px', fontSize: '13px', color: '#6b7280' }}>
        No account? <Link to="/register" style={{ color: '#7c6af7' }}>Create one</Link>
      </div>
    </div>
  )
}

export function RegisterPage() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const { login } = useAuth()
  const navigate = useNavigate()

  const submit = async e => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Registration failed')
      login(data.user, data.token)
      navigate('/workspace')
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }

  return (
    <div style={s.formCard}>
      <SEO title="Create Account" description="Create a free account on The Decoded Human to save research, track connections, and access the full Literature Connectome toolkit." path="/register" noindex={true} />
      <div style={s.formTitle}>Create account</div>
      <div style={s.formSub}>Save searches, build collections, set up alerts.</div>
      {error && <ErrorMsg msg={error} />}
      <form onSubmit={submit}>
        <label style={s.label}>Name</label>
        <input style={s.input} type="text" placeholder="Your name" value={name} onChange={e => setName(e.target.value)} required />
        <label style={s.label}>Email</label>
        <input style={s.input} type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} required />
        <label style={s.label}>Password</label>
        <input style={s.input} type="password" placeholder="At least 8 characters" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} />
        <button style={{ ...s.btn, width: '100%', padding: '10px', marginTop: '8px' }} type="submit" disabled={loading}>
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <div style={{ textAlign: 'center', marginTop: '16px', fontSize: '13px', color: '#6b7280' }}>
        Already have an account? <Link to="/login" style={{ color: '#7c6af7' }}>Sign in</Link>
      </div>
    </div>
  )
}

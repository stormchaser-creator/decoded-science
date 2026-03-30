import React, { useState, useEffect, useRef } from 'react'
import { API, s, authFetch } from '../shared.js'

const MODEL_OPTIONS = [
  { id: 'claude-sonnet-4-6', label: 'Sonnet', desc: 'Deep analysis', color: '#7c6af7' },
  { id: 'claude-haiku-4-5-20251001', label: 'Haiku', desc: 'Fast & cheap', color: '#4ade80' },
  { id: 'gpt-4o', label: 'GPT-4o', desc: 'OpenAI', color: '#60a5fa' },
  { id: 'grok-3', label: 'Grok 3', desc: 'xAI', color: '#f59e0b' },
]

const SUGGESTED_QUESTIONS = [
  "What are the clinical implications?",
  "How does this connect to related work in the corpus?",
  "What are the main methodological limitations?",
  "What experiments would strengthen these findings?",
  "Summarize this for a non-specialist",
]

export default function ChatPanel({ paperId, token, connections }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [model, setModel] = useState('claude-sonnet-4-6')
  const [loading, setLoading] = useState(false)
  const [totalCost, setTotalCost] = useState(0)
  const [isOpen, setIsOpen] = useState(true)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  // Load chat history
  useEffect(() => {
    if (!token || !paperId) return
    fetch(`${API}/v1/chat/${paperId}/history`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : { messages: [] })
      .then(data => {
        if (data.messages?.length) {
          setMessages(data.messages.map(m => ({
            role: m.role,
            content: m.content,
            model: m.model,
            cost: m.cost_usd,
          })))
          setTotalCost(data.messages.reduce((sum, m) => sum + (m.cost_usd || 0), 0))
        }
      })
      .catch(() => {})
  }, [paperId, token])

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  // Dynamic suggested questions based on connections
  const dynamicSuggestions = [...SUGGESTED_QUESTIONS]
  if (connections?.some(c => c.connection_type === 'contradicts')) {
    dynamicSuggestions.unshift("What do the contradicting papers say differently?")
  }

  const sendMessage = async (text) => {
    const msg = text || input.trim()
    if (!msg || loading) return

    const userMsg = { role: 'user', content: msg }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setInput('')
    setLoading(true)

    // Add streaming placeholder
    const assistantMsg = { role: 'assistant', content: '', model, cost: 0 }
    setMessages([...newMessages, assistantMsg])

    try {
      const response = await fetch(`${API}/v1/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          paper_id: paperId,
          message: msg,
          model,
          history: messages.slice(-10).map(m => ({ role: m.role, content: m.content })),
        }),
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Chat request failed' }))
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = { role: 'assistant', content: `Error: ${err.detail || 'Request failed'}`, model }
          return updated
        })
        setLoading(false)
        return
      }

      // Stream the response
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const chunk = JSON.parse(line.slice(6))
            if (chunk.delta) {
              fullText += chunk.delta
              setMessages(prev => {
                const updated = [...prev]
                updated[updated.length - 1] = { ...updated[updated.length - 1], content: fullText }
                return updated
              })
            }
            if (chunk.done) {
              setMessages(prev => {
                const updated = [...prev]
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  content: fullText,
                  cost: chunk.cost_usd || 0,
                }
                return updated
              })
              setTotalCost(prev => prev + (chunk.cost_usd || 0))
            }
            if (chunk.error) {
              setMessages(prev => {
                const updated = [...prev]
                updated[updated.length - 1] = { role: 'assistant', content: `Error: ${chunk.error}`, model }
                return updated
              })
            }
          } catch {}
        }
      }
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev]
        updated[updated.length - 1] = { role: 'assistant', content: `Error: ${err.message}`, model }
        return updated
      })
    }

    setLoading(false)
    setTimeout(() => inputRef.current?.focus(), 100)
  }

  const selectedModel = MODEL_OPTIONS.find(m => m.id === model) || MODEL_OPTIONS[0]

  return (
    <div style={{ ...s.card, marginTop: '12px' }}>
      {/* Header */}
      <div
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setIsOpen(!isOpen)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '18px' }}>&#9889;</span>
          <span style={{ ...s.sectionTitle, margin: 0 }}>Ask AI</span>
          <span style={{
            fontSize: '10px', padding: '2px 8px', borderRadius: '10px',
            background: selectedModel.color + '22', color: selectedModel.color,
            fontWeight: '600',
          }}>
            {selectedModel.label}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {totalCost > 0 && (
            <span style={{ fontSize: '10px', color: '#4b4b6b' }}>${totalCost.toFixed(3)} spent</span>
          )}
          <span style={{ fontSize: '16px', color: '#7c6af7' }}>{isOpen ? '\u2212' : '+'}</span>
        </div>
      </div>

      {isOpen && (
        <div style={{ marginTop: '12px' }}>
          {/* Model selector */}
          <div style={{ display: 'flex', gap: '6px', marginBottom: '12px', flexWrap: 'wrap' }}>
            {MODEL_OPTIONS.map(m => (
              <button
                key={m.id}
                onClick={() => setModel(m.id)}
                style={{
                  background: model === m.id ? m.color + '22' : 'transparent',
                  border: `1px solid ${model === m.id ? m.color : '#2d2060'}`,
                  color: model === m.id ? m.color : '#6b7280',
                  borderRadius: '16px', padding: '4px 12px', fontSize: '11px',
                  cursor: 'pointer', fontWeight: model === m.id ? '600' : '400',
                  transition: 'all 0.15s',
                }}
              >
                {m.label}
                <span style={{ fontSize: '9px', marginLeft: '4px', opacity: 0.7 }}>{m.desc}</span>
              </button>
            ))}
          </div>

          {/* Messages */}
          <div
            ref={scrollRef}
            style={{
              maxHeight: '400px', overflowY: 'auto', marginBottom: '12px',
              borderRadius: '8px', background: '#0a0a14', padding: messages.length ? '8px' : '0',
            }}
          >
            {messages.map((m, i) => (
              <div key={i} style={{
                marginBottom: '8px', padding: '10px 12px',
                background: m.role === 'user' ? '#1a1a2e' : '#0e0e1a',
                borderLeft: `3px solid ${m.role === 'user' ? '#7c6af7' : '#4ade80'}`,
                borderRadius: '4px', fontSize: '12px', color: '#c4bef8',
                lineHeight: '1.7', whiteSpace: 'pre-wrap',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ fontSize: '10px', fontWeight: '600', color: m.role === 'user' ? '#7c6af7' : '#4ade80', textTransform: 'uppercase' }}>
                    {m.role === 'user' ? 'You' : m.model ? MODEL_OPTIONS.find(o => o.id === m.model)?.label || m.model : 'AI'}
                  </span>
                  {m.cost > 0 && (
                    <span style={{ fontSize: '9px', color: '#4b4b6b' }}>${m.cost.toFixed(4)}</span>
                  )}
                </div>
                {m.content || (loading && i === messages.length - 1 ? (
                  <span style={{ color: '#4b4b6b', fontStyle: 'italic' }}>Thinking...</span>
                ) : '')}
              </div>
            ))}
          </div>

          {/* Suggested questions (only show when no messages) */}
          {messages.length === 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '12px' }}>
              {dynamicSuggestions.slice(0, 4).map((q, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(q)}
                  disabled={loading}
                  style={{
                    background: '#1a1a2e', border: '1px solid #2d2060', color: '#9991d0',
                    borderRadius: '16px', padding: '6px 12px', fontSize: '11px',
                    cursor: 'pointer', transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = '#7c6af7'; e.currentTarget.style.color = '#c4bef8' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = '#2d2060'; e.currentTarget.style.color = '#9991d0' }}
                >
                  {q}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              ref={inputRef}
              style={{ ...s.input, marginBottom: 0, flex: 1, fontSize: '13px' }}
              placeholder="Ask about this paper..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && !loading && sendMessage()}
              disabled={loading}
            />
            <button
              style={{
                ...s.btn, padding: '8px 16px', opacity: loading || !input.trim() ? 0.5 : 1,
                cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
              }}
              onClick={() => sendMessage()}
              disabled={loading || !input.trim()}
            >
              {loading ? '...' : 'Send'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

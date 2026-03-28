import React, { createContext, useContext, useState } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('decoded_user')) } catch { return null }
  })
  const [token, setToken] = useState(() => localStorage.getItem('decoded_token') || null)

  const login = (u, t) => {
    setUser(u)
    setToken(t)
    localStorage.setItem('decoded_user', JSON.stringify(u))
    localStorage.setItem('decoded_token', t)
  }
  const logout = () => {
    setUser(null)
    setToken(null)
    localStorage.removeItem('decoded_user')
    localStorage.removeItem('decoded_token')
  }

  return <AuthContext.Provider value={{ user, token, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() { return useContext(AuthContext) }

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from './api'
import { AuthContext, type AuthValue } from './auth'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<string | null>(null)
  const [role, setRole] = useState('student')
  const [school, setSchool] = useState('')
  const [ready, setReady] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const d = await api.me()
      setUser(d.user)
      setRole(d.role || 'student')
      setSchool(d.school || '')
    } catch {
      setUser(null)
      setRole('student')
      setSchool('')
    } finally {
      setReady(true)
    }
  }, [])

  // Initial identity check — intentionally runs once on mount.
  useEffect(() => {
    void refresh()
  }, [refresh])

  const login = useCallback(
    async (username: string, password: string) => {
      await api.login(username, password)
      await refresh()
    },
    [refresh],
  )

  const register = useCallback(
    async (username: string, password: string, role: string, schoolName?: string) => {
      await api.register(username, password, role, schoolName)
      await refresh()
    },
    [refresh],
  )

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setUser(null)
      setRole('student')
      setSchool('')
    }
  }, [])

  const value = useMemo<AuthValue>(
    () => ({ user, role, school, ready, login, register, logout, refresh }),
    [user, role, school, ready, login, register, logout, refresh],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

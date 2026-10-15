import { createContext, useContext } from 'react'

export interface AuthValue {
  user: string | null
  role: string
  school: string
  /** false until the initial /api/me check resolves — gate auth-dependent UI on this. */
  ready: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, role: string, school?: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

export const AuthContext = createContext<AuthValue | null>(null)

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}

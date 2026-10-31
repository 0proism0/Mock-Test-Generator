import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  ThemeContext,
  applyTheme,
  readStoredTheme,
  resolveTheme,
  storeTheme,
  type Theme,
  type ThemePref,
  type ThemeValue,
} from './theme'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>(readStoredTheme)
  const [theme, setTheme] = useState<Theme>(() => resolveTheme(readStoredTheme()))

  // Paint <html data-theme> — the inline script in index.html already did this once
  // before first paint, so this only has to handle later changes.
  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  // Follow the OS, but only while the preference is "system".
  useEffect(() => {
    if (pref !== 'system') return
    let mq: MediaQueryList
    try {
      mq = window.matchMedia('(prefers-color-scheme: dark)')
    } catch {
      return
    }
    const onChange = () => setTheme(mq.matches ? 'dark' : 'light')
    onChange() // catch a change that happened between the initial read and now
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [pref])

  const setPref = useCallback((next: ThemePref) => {
    setPrefState(next)
    storeTheme(next)
    setTheme(resolveTheme(next))
  }, [])

  const toggle = useCallback(() => {
    setPref(theme === 'dark' ? 'light' : 'dark')
  }, [theme, setPref])

  const value = useMemo<ThemeValue>(() => ({ pref, theme, setPref, toggle }), [pref, theme, setPref, toggle])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

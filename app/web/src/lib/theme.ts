import { createContext, useContext } from 'react'

/** What the user picked. "system" defers to the OS `prefers-color-scheme`. */
export type ThemePref = 'light' | 'dark' | 'system'
/** What is actually painted. */
export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'mt_theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'

export function readStoredTheme(): ThemePref {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === 'light' || v === 'dark' || v === 'system' ? v : 'system'
  } catch {
    return 'system' // storage unavailable (private mode) — fall back to the OS
  }
}

export function storeTheme(pref: ThemePref): void {
  try {
    localStorage.setItem(STORAGE_KEY, pref)
  } catch {
    /* storage unavailable — the choice just won't persist */
  }
}

export function systemTheme(): Theme {
  try {
    return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function resolveTheme(pref: ThemePref): Theme {
  return pref === 'system' ? systemTheme() : pref
}

/**
 * Paint the resolved theme onto <html>.
 * Keep this in sync with the pre-paint snippet in index.html (it can't import TS).
 */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  root.dataset.theme = theme
  root.style.colorScheme = theme
}

export interface ThemeValue {
  /** The stored preference (may be "system"). */
  pref: ThemePref
  /** The theme actually in effect. */
  theme: Theme
  setPref: (pref: ThemePref) => void
  /** Flip between light and dark (leaves "system" behind, as a click is an explicit choice). */
  toggle: () => void
}

export const ThemeContext = createContext<ThemeValue | null>(null)

export function useTheme(): ThemeValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider')
  return ctx
}

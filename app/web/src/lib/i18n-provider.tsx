import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  I18nContext,
  readStoredLang,
  storeLang,
  stripLeadingEmoji,
  translate,
  type I18nValue,
  type Lang,
} from './i18n'

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readStoredLang)

  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  }, [lang])

  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    storeLang(next)
  }, [])

  const t = useCallback((key: string, ...args: (string | number)[]) => translate(lang, key, ...args), [lang])
  const tip = useCallback((key: string) => stripLeadingEmoji(t(key)), [t])

  const value = useMemo<I18nValue>(() => ({ lang, setLang, t, tip }), [lang, setLang, t, tip])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

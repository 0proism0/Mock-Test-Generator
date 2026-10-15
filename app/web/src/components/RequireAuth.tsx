import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

/** Gates auth-only routes (legacy showed an "auth required" card on those tabs). */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  const { user, ready } = useAuth()

  if (!ready) {
    return (
      <section className="card">
        <p className="muted">{t('loading')}</p>
      </section>
    )
  }
  if (!user) {
    return (
      <section className="card">
        <p className="muted">{t('authRequired')}</p>
        <p style={{ marginTop: 12 }}>
          <Link className="btn" to="/login">
            {t('login')} / {t('register')}
          </Link>
        </p>
      </section>
    )
  }
  return <>{children}</>
}

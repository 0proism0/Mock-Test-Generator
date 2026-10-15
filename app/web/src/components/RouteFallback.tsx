import { useI18n } from '../lib/i18n'

/** Shown while a lazily-loaded route chunk is fetched. */
export function RouteFallback() {
  const { t } = useI18n()
  return (
    <section className="card">
      <p className="muted">{t('loading')}</p>
    </section>
  )
}

import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

interface CompStat {
  competition: string
  attempts: number
  avg_pct: number | null
  best_pct: number | null
}

interface StatsData {
  total_attempts: number
  total_questions_answered: number
  avg_pct: number | null
  per_competition: CompStat[]
}

/** Legacy "Stats" tab. */
export function Stats() {
  const { t } = useI18n()
  const [stats, setStats] = useState<StatsData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .stats()
      .then((d) => setStats(d as StatsData))
      .catch((e: unknown) => setError(String(e)))
  }, [])

  if (error) {
    return (
      <section className="card">
        <p className="status err">API error: {error}</p>
      </section>
    )
  }
  if (!stats) {
    return (
      <section className="card">
        <p className="muted">{t('loading')}</p>
      </section>
    )
  }

  return (
    <>
      <div className="card" style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
        <div>
          <div className="score">{stats.total_attempts}</div>
          <div className="meta">{t('testsTaken')}</div>
        </div>
        <div>
          <div className="score">{stats.total_questions_answered}</div>
          <div className="meta">{t('questionsAnswered')}</div>
        </div>
        <div>
          <div className="score">{stats.avg_pct !== null ? `${stats.avg_pct}%` : '–'}</div>
          <div className="meta">{t('averageScore')}</div>
        </div>
      </div>
      <div className="card">
        <h3 style={{ marginBottom: 10 }}>{t('byCompetition')}</h3>
        {stats.per_competition.length ? (
          <table className="stats">
            <tbody>
              <tr>
                <th>{t('competition')}</th>
                <th>{t('attempts')}</th>
                <th>{t('average')}</th>
                <th>{t('best')}</th>
              </tr>
              {stats.per_competition.map((c) => (
                <tr key={c.competition}>
                  <td>{c.competition}</td>
                  <td>{c.attempts}</td>
                  <td>
                    {c.avg_pct ?? '–'}
                    {c.avg_pct !== null ? '%' : ''}{' '}
                    <span className="pct-bar">
                      <div style={{ width: `${c.avg_pct ?? 0}%` }} />
                    </span>
                  </td>
                  <td>
                    {c.best_pct ?? '–'}
                    {c.best_pct !== null ? '%' : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          t('noAttempts')
        )}
      </div>
    </>
  )
}

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type TestResult, type TestSummary } from '../lib/api'
import { useI18n } from '../lib/i18n'

/** Legacy "My Tests" tab: current tests + past attempts. */
export function MyTests() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const [tests, setTests] = useState<TestSummary[] | null>(null)
  const [results, setResults] = useState<TestResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.tests(), api.results()])
      .then(([ts, rs]) => {
        setTests(ts)
        setResults([...rs].reverse())
      })
      .catch((e: unknown) => setError(String(e)))
  }, [])

  if (error) {
    return (
      <section className="card">
        <p className="status err">API error: {error}</p>
      </section>
    )
  }
  if (!tests || !results) {
    return (
      <section className="card">
        <p className="muted">{t('loading')}</p>
      </section>
    )
  }

  return (
    <>
      <h2 className="section-title">{t('currentTests')}</h2>
      <div className="gen-grid">
        {tests.map((tst) => (
          <div key={tst.id} className="card compact test-item" onClick={() => navigate(`/test/${tst.id}`)}>
            <div>
              <h3>{tst.title}</h3>
              <div className="meta">
                {tst.competition} · {tst.n_questions} {t('questions')} · {tst.time_limit_min} {t('min')}
              </div>
            </div>
            <button className="btn" type="button">
              {t('start')}
            </button>
          </div>
        ))}
        {!tests.length && <div className="card compact">{t('noTests')}</div>}
      </div>
      <h2 className="section-title">{t('pastTests')}</h2>
      {!results.length ? (
        <div className="card compact">{t('noAttempts')}</div>
      ) : (
        results.map((r) => {
          const pct = r.total ? Math.round((r.score / r.total) * 100) : null
          const dur = r.duration_s ? `${Math.floor(r.duration_s / 60)}m${r.duration_s % 60}s` : '–'
          return (
            <div key={`${r.test_id}-${r.submitted_at}`} className="card compact test-item">
              <div>
                <h3>{r.title || r.test_id}</h3>
                <div className="meta">
                  {r.competition} · {t('submitted')} {r.submitted_at} · {r.answered}/{r.total || '?'}{' '}
                  {t('answered')} · {dur}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
                {pct !== null ? (
                  <span className="score" style={{ fontSize: 18 }}>
                    {pct}%
                  </span>
                ) : (
                  <span className="meta">{t('proof')}</span>
                )}
                <button className="btn" type="button" onClick={() => navigate(`/test/${r.test_id}`)}>
                  {t('retake')}
                </button>
              </div>
            </div>
          )
        })
      )}
    </>
  )
}

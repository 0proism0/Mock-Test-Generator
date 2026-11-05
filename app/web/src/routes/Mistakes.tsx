import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AutoMath } from '../components/AutoMath'
import { Crosshair } from '../components/icons'
import {
  abilityProfile,
  collectMissed,
  loadAnalysisData,
  makeKpResolver,
  type ClassMap,
  type AnTest,
} from '../lib/analysis'
import { api, type Taxonomy, type TestResult } from '../lib/api'
import { useI18n } from '../lib/i18n'

export function Mistakes() {
  const { t, lang } = useI18n()
  const navigate = useNavigate()
  const [results, setResults] = useState<TestResult[] | null>(null)
  const [tests, setTests] = useState<Record<string, AnTest>>({})
  const [classes, setClasses] = useState<Record<string, ClassMap>>({})
  const [tax, setTax] = useState<Taxonomy | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.taxonomy().then(setTax).catch(() => {})
    api
      .results()
      .then(async (rs) => {
        setResults(rs)
        const data = await loadAnalysisData(rs)
        setTests(data.tests)
        setClasses(data.classes)
      })
      .catch(() => setResults([]))
  }, [])

  const resolve = useMemo(
    () => makeKpResolver(tests, classes, tax, lang),
    [tests, classes, tax, lang],
  )

  const missed = useMemo(
    () => (results ? collectMissed(results, tests, resolve) : []),
    [results, tests, resolve],
  )
  const profile = useMemo(
    () => (results ? abilityProfile(results, resolve) : []),
    [results, resolve],
  )
  const weakness = profile.filter((p) => p.pct < 60)
  const strengths = profile.filter((p) => p.pct >= 80 && p.total >= 2)

  /** unique (test_id, n) pairs, newest occurrence wins — these feed the similar-practice generator */
  const uniqueTargets = useMemo(() => {
    const seen = new Map<string, { test_id: string; n: number }>()
    for (const m of missed) {
      const key = `${m.test_id}:${m.n}`
      if (!seen.has(key)) seen.set(key, { test_id: m.test_id, n: m.n })
    }
    return [...seen.values()].slice(0, 25)
  }, [missed])

  async function practiceSimilar(items: { test_id: string; n: number }[]) {
    setBusy(true)
    setError('')
    try {
      const d = await api.practiceSimilar(items)
      navigate(`/test/${d.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (results === null) return <section className="card"><p className="muted">{t('loading')}</p></section>

  return (
    <div className="an-page">
      {/* overall profile check */}
      <section className="card an-report">
        <h3>{t('anAbility')}</h3>
        {profile.length === 0 ? (
          <p className="muted">{t('anNoCls')}</p>
        ) : (
          <>
            {strengths.length > 0 && (
              <p>
                <b>{t('anStrengths')}:</b> {strengths.map((s) => `${s.kp} (${s.pct}%)`).join(' · ')}
              </p>
            )}
            {weakness.length > 0 && (
              <div className="an-kp-list">
                <b>{t('anWeakness')}:</b>
                {weakness.map((w) => (
                  <div key={w.kp} className="an-kp-row">
                    <span className="an-kp-name">{w.kp}</span>
                    <span className="pct-bar">
                      <span style={{ width: `${w.pct}%` }} className={w.pct < 40 ? 'low' : ''} />
                    </span>
                    <span className="meta">
                      {w.ok}/{w.total} · {w.pct}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
        <div className="an-cls-actions">
          <button
            type="button"
            className="btn"
            disabled={busy || uniqueTargets.length === 0}
            onClick={() => void practiceSimilar(uniqueTargets)}
          >
            <Crosshair size={15} /> {t('anPracticeAll')} ({uniqueTargets.length})
          </button>
          {error && <span className="status err">{error}</span>}
        </div>
      </section>

      {/* wrong questions list */}
      <section className="card">
        <h3>{t('tabMistakes')}</h3>
        {missed.length === 0 ? (
          <p className="muted">{t('anNoMistakes')}</p>
        ) : (
          <div className="ms-list">
            {missed.map((m, i) => (
              <div key={`${m.test_id}-${m.submitted_at}-${m.n}-${i}`} className="ms-item">
                <div className="ms-meta">
                  <span className="ms-badge">
                    {m.test_title} · #{m.n}
                  </span>
                  <span className="ms-kp">{m.kp}</span>
                  {m.diff != null && <span className="ms-badge">{t('difficulty')} {m.diff}</span>}
                  <span className="meta">
                    {t('anMyAns')}: <b>{m.given || t('anUnanswered')}</b> → {String(m.answer)}
                  </span>
                  <button
                    type="button"
                    className="btn sm ghost"
                    disabled={busy}
                    onClick={() => void practiceSimilar([{ test_id: m.test_id, n: m.n }])}
                  >
                    <Crosshair size={13} /> {t('anPracticeSimilar')}
                  </button>
                </div>
                <AutoMath className="ms-q" html={m.question} />
                {m.note && <p className="ms-note">{t('anKeyPoint')}: {m.note}</p>}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

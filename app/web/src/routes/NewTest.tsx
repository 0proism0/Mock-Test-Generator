import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CategoryIcon } from '../components/CategoryIcon'
import { api, type Bank } from '../lib/api'
import { useI18n } from '../lib/i18n'

const CATEGORY_ORDER = [
  'Math',
  'Physics',
  'Chemistry',
  'Biology',
  'Informatics',
  'Astronomy & Earth',
  'Economics',
  'Linguistics',
  'Other',
]

type View =
  | { kind: 'families' }
  | { kind: 'family'; family: string }
  | { kind: 'detail'; slug: string; round: string | null }

/** Legacy "New Test" tab: category → family → competition picker, then generate. */
export function NewTest() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const [banks, setBanks] = useState<Bank[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [genError, setGenError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<View>({ kind: 'families' })

  useEffect(() => {
    api
      .banks()
      .then(setBanks)
      .catch((e: unknown) => setLoadError(String(e)))
  }, [])

  const families = useMemo(() => {
    const byCategory: Record<string, Record<string, Bank[]>> = {}
    for (const b of banks ?? []) {
      const category = b.category ?? 'Other'
      byCategory[category] ??= {}
      byCategory[category][b.family ?? ''] ??= []
      byCategory[category][b.family ?? ''].push(b)
    }
    return byCategory
  }, [banks])

  async function onGenerate(b: Bank) {
    setBusy(true)
    setGenError(null)
    try {
      const r = await api.generate(b.slug, b.round)
      navigate(`/test/${r.id}`)
    } catch (e) {
      setGenError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (loadError) {
    return (
      <section className="card">
        <p className="status err">API error: {loadError}</p>
      </section>
    )
  }
  if (!banks) {
    return (
      <section className="card">
        <p className="muted">{t('loading')}</p>
      </section>
    )
  }

  if (view.kind === 'families') {
    const categories = CATEGORY_ORDER.filter((c) => families[c])
    return (
      <>
        {categories.map((category) => (
          <section key={category}>
            <h2 className="section-title">
              <CategoryIcon category={category} />
              {category}
            </h2>
            <div className="gen-grid">
              {Object.entries(families[category]).map(([family, subs]) => {
                const nProblems = subs.reduce((sum, b) => sum + (b.total_variants ?? 0), 0)
                return (
                  <div
                    key={family}
                    className="card compact test-item"
                    onClick={() => setView({ kind: 'family', family })}
                  >
                    <div>
                      <h3>{family}</h3>
                      <div className="meta">
                        {subs.length} {t('tests')} ·{' '}
                        {subs.some((b) => b.real) ? t('realProblem') : t('modifiedFrom')} {nProblems}+{' '}
                        {t('problems')}
                      </div>
                    </div>
                    <button className="btn" type="button">
                      ›
                    </button>
                  </div>
                )
              })}
            </div>
          </section>
        ))}
        <div className="card compact disclaimer" dangerouslySetInnerHTML={{ __html: t('disclaimer') }} />
      </>
    )
  }

  if (view.kind === 'family') {
    const subs = banks.filter((b) => b.family === view.family)
    const category = subs[0]?.category ?? ''
    return (
      <>
        <div className="card compact back" onClick={() => setView({ kind: 'families' })}>
          {t('backAll')}
        </div>
        <h2 className="section-title">
          <CategoryIcon category={category} />
          {view.family}
        </h2>
        <div className="gen-grid">
          {subs.map((b) => (
            <div
              key={`${b.slug}-${b.round ?? ''}`}
              className="card compact test-item"
              onClick={() => setView({ kind: 'detail', slug: b.slug, round: b.round ?? null })}
            >
              <div>
                <h3>{b.name}</h3>
                <div className="meta">
                  {b.n_questions} {t('questions')} · {b.time_limit_min} {t('min')} · {b.total_variants}{' '}
                  {t('problems')}
                </div>
              </div>
              <button className="btn" type="button">
                ›
              </button>
            </div>
          ))}
        </div>
      </>
    )
  }

  const b = banks.find((x) => x.slug === view.slug && (x.round ?? null) === view.round)
  if (!b) {
    return (
      <div className="card compact back" onClick={() => setView({ kind: 'families' })}>
        {t('backAll')}
      </div>
    )
  }
  const types = b.real || (b.total_variants ?? 0) >= 300 ? t('realProblem') : t('modifiedFrom')
  return (
    <>
      <div className="card compact back" onClick={() => setView({ kind: 'family', family: b.family ?? '' })}>
        {t('back')} {b.family}
      </div>
      <section className="card">
        <h2>{b.name}</h2>
        <table className="stats" style={{ marginTop: 12 }}>
          <tbody>
            <tr>
              <th>{t('category')}</th>
              <td>{b.category}</td>
            </tr>
            <tr>
              <th>{t('questions')}</th>
              <td>{b.n_questions}</td>
            </tr>
            <tr>
              <th>{t('timeLimit')}</th>
              <td>
                {b.time_limit_min} {t('minutes')}
              </td>
            </tr>
            <tr>
              <th>{t('bank')}</th>
              <td>
                {types} {b.total_variants}+ {t('problems')}
              </td>
            </tr>
            <tr>
              <th>{t('content')}</th>
              <td>{types}</td>
            </tr>
          </tbody>
        </table>
        <div style={{ marginTop: 18 }}>
          <button
            className="btn"
            type="button"
            style={{ fontSize: 16, padding: '12px 28px' }}
            disabled={busy}
            onClick={() => void onGenerate(b)}
          >
            {t('generate')}
          </button>
        </div>
        {genError && (
          <p className="status err" style={{ marginTop: 10 }}>
            {genError}
          </p>
        )}
      </section>
    </>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CategoryIcon } from '../components/CategoryIcon'
import { ArrowLeft, ArrowRight } from '../components/icons'
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

/** 1 = classic bank, 2 = figure bank (bank/v2). Persisted so the choice sticks. */
type BankVersion = 1 | 2

const VERSION_KEY = 'mt_bank_version'

function readStoredVersion(): BankVersion {
  try {
    return localStorage.getItem(VERSION_KEY) === '2' ? 2 : 1
  } catch {
    return 1
  }
}

/** Bank-version switch. v2 is disabled when that competition has no figure bank. */
function VersionPicker({
  value,
  onChange,
  bank,
}: {
  value: BankVersion
  onChange: (v: BankVersion) => void
  bank?: Bank
}) {
  const { t } = useI18n()
  // Global picker (no bank yet): both choices stay selectable as a preference.
  // On a competition page the figure option is disabled when that bank is missing.
  const hasV2 = bank ? (bank.versions ?? [1]).includes(2) : true
  return (
    <div className="bank-version">
      <span className="bank-version-label">{t('bankVersion')}</span>
      <div className="seg">
        <button
          type="button"
          className={`seg-btn${value === 1 ? ' on' : ''}`}
          onClick={() => onChange(1)}
        >
          {t('bankV1')}
        </button>
        <button
          type="button"
          className={`seg-btn${value === 2 ? ' on' : ''}`}
          disabled={!hasV2}
          title={hasV2 ? undefined : t('v2Unavailable')}
          onClick={() => {
            if (hasV2) onChange(2)
          }}
        >
          {t('bankV2')}
        </button>
      </div>
      {bank ? (
        <span className="muted bank-version-hint">
          {hasV2 && bank.v2_figures ? t('v2Figures', bank.v2_figures) : t('v2Unavailable')}
        </span>
      ) : null}
    </div>
  )
}

/** Legacy "New Test" tab: category → family → competition picker, then generate. */
export function NewTest() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const [banks, setBanks] = useState<Bank[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [genError, setGenError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<View>({ kind: 'families' })
  const [version, setVersion] = useState<BankVersion>(readStoredVersion)

  function pickVersion(v: BankVersion) {
    setVersion(v)
    try {
      localStorage.setItem(VERSION_KEY, String(v))
    } catch {
      /* storage unavailable (private mode) — the choice just won't persist */
    }
  }

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
      // Ask for the figure bank only when this competition actually has one;
      // the server falls back to the classic bank if the request fails anyway.
      const want: BankVersion = version === 2 && (b.versions ?? [1]).includes(2) ? 2 : 1
      const r = await api.generate(b.slug, b.round, want)
      // Tell the runner when the server had to fall back to the classic bank.
      navigate(`/test/${r.id}`, { state: r.fallback ? { fallback: true } : undefined })
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
        <VersionPicker value={version} onChange={pickVersion} />
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
          <ArrowLeft size={14} aria-hidden="true" /> {t('backAll')}
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
        <ArrowLeft size={14} aria-hidden="true" /> {t('back')} {b.family}
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
        <VersionPicker value={version} onChange={pickVersion} bank={b} />
        <div style={{ marginTop: 18 }}>
          <button
            className="btn"
            type="button"
            style={{ fontSize: 16, padding: '12px 28px' }}
            disabled={busy}
            onClick={() => void onGenerate(b)}
          >
            {t('generate')} <ArrowRight size={16} aria-hidden="true" />
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

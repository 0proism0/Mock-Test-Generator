import { useCallback, useEffect, useMemo, useState } from 'react'
import { AutoMath } from '../components/AutoMath'
import { ReportIssue } from '../components/ReportIssue'
import { ArrowLeft, ArrowRight, Search, Tag } from '../components/icons'
import { api, type QuestionPage, type QuestionRow, type Taxonomy } from '../lib/api'
import { useI18n } from '../lib/i18n'

const PAGE_SIZE = 25
const LEVELS = Array.from({ length: 20 }, (_, i) => i + 1)
const TYPES = ['multiple_choice', 'integer_answer', 'numeric', 'proof']

/** Search + filter over every question in every bank (GET /api/questions). */
export function Bank() {
  const { t, lang } = useI18n()

  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [comp, setComp] = useState('')
  const [version, setVersion] = useState('')
  const [domain, setDomain] = useState('')
  const [levelMin, setLevelMin] = useState('')
  const [levelMax, setLevelMax] = useState('')
  const [qtype, setQtype] = useState('')
  const [figureOnly, setFigureOnly] = useState(false)
  const [classifiedOnly, setClassifiedOnly] = useState(false)
  const [sort, setSort] = useState('default')
  const [offset, setOffset] = useState(0)

  const [page, setPage] = useState<QuestionPage | null>(null)
  const [tax, setTax] = useState<Taxonomy | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [open, setOpen] = useState<Record<string, boolean>>({})

  // Search as you type, but do not hammer the server on every keystroke.
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query), 250)
    return () => window.clearTimeout(id)
  }, [query])

  // Any filter change starts a new result set.
  useEffect(() => {
    setOffset(0)
  }, [debounced, comp, version, domain, levelMin, levelMax, qtype, figureOnly, classifiedOnly, sort])

  useEffect(() => {
    let dead = false
    setLoading(true)
    api
      .questions({
        q: debounced,
        comp,
        v: version,
        domain,
        level_min: levelMin,
        level_max: levelMax,
        type: qtype,
        figure: figureOnly,
        classified: classifiedOnly,
        sort,
        limit: PAGE_SIZE,
        offset,
      })
      .then((data) => {
        if (dead) return
        setPage(data)
        setError('')
      })
      .catch((e: unknown) => {
        if (!dead) setError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!dead) setLoading(false)
      })
    return () => {
      dead = true
    }
  }, [debounced, comp, version, domain, levelMin, levelMax, qtype, figureOnly, classifiedOnly, sort, offset])

  useEffect(() => {
    api
      .taxonomy()
      .then(setTax)
      .catch(() => setTax(null))
  }, [])

  const label = useCallback(
    (id: string | null): string => {
      if (!id) return ''
      const node = tax?.nodes[id]
      if (!node) return id
      return lang === 'zh' ? node.zh || node.en : node.en || node.zh
    },
    [tax, lang],
  )

  const typeLabel = (type: string) => {
    switch (type) {
      case 'multiple_choice':
        return t('qbTypeMultipleChoice')
      case 'integer_answer':
        return t('qbTypeInteger')
      case 'numeric':
        return t('qbTypeNumeric')
      case 'proof':
        return t('qbTypeProof')
      default:
        return type || t('qbTypeUnknown')
    }
  }

  const counts = page?.counts
  const total = page?.total ?? 0
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE_SIZE, total)
  const domains = useMemo(() => Object.entries(counts?.domain ?? {}), [counts])
  const comps = useMemo(() => Object.entries(counts?.competition ?? {}), [counts])

  const reset = () => {
    setQuery('')
    setDebounced('')
    setComp('')
    setVersion('')
    setDomain('')
    setLevelMin('')
    setLevelMax('')
    setQtype('')
    setFigureOnly(false)
    setClassifiedOnly(false)
    setSort('default')
    setOffset(0)
  }

  return (
    <>
      <div className="qb-head">
        <div>
          <h2 className="qb-title">{t('qbTitle')}</h2>
          <p className="muted">{t('qbSubtitle')}</p>
        </div>
        {counts && (
          <span className="muted qb-total">
            {counts.all.toLocaleString()} {t('qbTotal')}
          </span>
        )}
      </div>

      <section className="card qb-bar">
        <div className="qb-search">
          <Search size={16} aria-hidden="true" />
          <input
            className="qb-input"
            type="search"
            value={query}
            placeholder={t('qbSearch')}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button type="button" className="link qb-clear" onClick={() => setQuery('')}>
              {t('qbClear')}
            </button>
          )}
        </div>

        <div className="qb-filters">
          <label className="qb-field">
            <span>{t('qbCompetition')}</span>
            <select value={comp} onChange={(e) => setComp(e.target.value)}>
              <option value="">{t('qbAllCompetitions')}</option>
              {comps.map(([slug, n]) => (
                <option key={slug} value={slug}>
                  {counts?.competition_labels?.[slug] ?? slug} ({n})
                </option>
              ))}
            </select>
          </label>

          <label className="qb-field">
            <span>{t('qbDomain')}</span>
            <select value={domain} onChange={(e) => setDomain(e.target.value)}>
              <option value="">{t('qbAllDomains')}</option>
              {domains.map(([id, n]) => (
                <option key={id} value={id}>
                  {label(id)} ({n})
                </option>
              ))}
            </select>
          </label>

          <label className="qb-field">
            <span>{t('qbLevel')}</span>
            <span className="qb-range">
              <select value={levelMin} onChange={(e) => setLevelMin(e.target.value)}>
                <option value="">{t('qbAny')}</option>
                {LEVELS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <span className="qb-dash">–</span>
              <select value={levelMax} onChange={(e) => setLevelMax(e.target.value)}>
                <option value="">{t('qbAny')}</option>
                {LEVELS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </span>
          </label>

          <label className="qb-field">
            <span>{t('qbType')}</span>
            <select value={qtype} onChange={(e) => setQtype(e.target.value)}>
              <option value="">{t('qbAllTypes')}</option>
              {TYPES.map((ty) => (
                <option key={ty} value={ty}>
                  {typeLabel(ty)}
                </option>
              ))}
            </select>
          </label>

          <label className="qb-field">
            <span>{t('qbBankVersion')}</span>
            <select value={version} onChange={(e) => setVersion(e.target.value)}>
              <option value="">{t('qbAllBanks')}</option>
              <option value="2">{t('qbBankV2')}</option>
              <option value="1">{t('qbBankV1')}</option>
            </select>
          </label>

          <label className="qb-field">
            <span>{t('qbSort')}</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="default">{t('qbSortDefault')}</option>
              <option value="level_asc">{t('qbSortLevelAsc')}</option>
              <option value="level_desc">{t('qbSortLevelDesc')}</option>
              <option value="position">{t('qbSortPosition')}</option>
            </select>
          </label>

          <label className="qb-check">
            <input type="checkbox" checked={figureOnly} onChange={(e) => setFigureOnly(e.target.checked)} />
            {t('qbFigureOnly')}
          </label>
          <label className="qb-check">
            <input type="checkbox" checked={classifiedOnly} onChange={(e) => setClassifiedOnly(e.target.checked)} />
            {t('qbClassifiedOnly')}
          </label>

          <button type="button" className="btn ghost sm qb-reset" onClick={reset}>
            {t('qbReset')}
          </button>
        </div>
      </section>

      {error && (
        <div className="card compact qb-error">
          {t('qbError')}: {error}
        </div>
      )}

      <div className="qb-summary">
        <span className="muted">
          {t('qbShowing')} {from}–{to} / {total.toLocaleString()}
          {loading ? ` · ${t('qbLoading')}` : ''}
        </span>
      </div>

      {page && page.items.length === 0 && !loading && <div className="card compact muted">{t('qbEmpty')}</div>}

      <div className="qb-list">
        {page?.items.map((row) => (
          <QuestionItem
            key={row.id}
            row={row}
            open={Boolean(open[row.id])}
            onToggle={() => setOpen((prev) => ({ ...prev, [row.id]: !prev[row.id] }))}
            label={label}
            typeLabel={typeLabel}
            bankLabel={row.version === 2 ? t('qbBankV2') : t('qbBankV1')}
          />
        ))}
      </div>

      {total > PAGE_SIZE && (
        <div className="qb-pager">
          <button
            type="button"
            className="btn ghost sm"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            <ArrowLeft size={14} aria-hidden="true" />
            {t('qbPrev')}
          </button>
          <span className="muted">
            {t('qbPage')} {Math.floor(offset / PAGE_SIZE) + 1} / {Math.ceil(total / PAGE_SIZE)}
          </span>
          <button
            type="button"
            className="btn ghost sm"
            disabled={to >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            {t('qbNext')}
            <ArrowRight size={14} aria-hidden="true" />
          </button>
        </div>
      )}
    </>
  )
}

interface QuestionItemProps {
  row: QuestionRow
  open: boolean
  onToggle: () => void
  label: (id: string | null) => string
  typeLabel: (type: string) => string
  bankLabel: string
}

function QuestionItem({ row, open, onToggle, label, typeLabel, bankLabel }: QuestionItemProps) {
  const { t } = useI18n()
  const bandClass = row.band === 'hard' ? 'hard' : row.band === 'medium' || row.band === 'mid' ? 'mid' : 'easy'
  const tags = row.tags.filter((id) => id !== row.primary)

  return (
    <article className={open ? 'card qb-item open' : 'card qb-item'}>
      <div className="qb-meta">
        {row.level !== null && <span className={`diff ${bandClass}`}>L{row.level}</span>}
        {row.primary && (
          <span className="badge topic" title={row.primary}>
            <Tag size={11} aria-hidden="true" />
            {label(row.primary)}
          </span>
        )}
        <span className="badge">{typeLabel(row.type)}</span>
        <span className="badge">{bankLabel}</span>
        {row.has_figure && <span className="badge">{t('qbHasFigure')}</span>}
        {row.points ? <span className="badge">{row.points} pts</span> : null}
        <span className="qb-src">
          {row.competition}
          {row.set ? ` · ${row.set}` : ''} · {row.source || `#${row.position ?? '?'}`}
        </span>
      </div>

      <AutoMath html={row.question || '—'} className="qb-text" />

      {row.has_figure && row.figure?.src && (
        <img className="qb-fig" src={row.figure.src} alt={row.figure.alt ?? ''} loading="lazy" />
      )}

      <div className="qb-actions">
        <button type="button" className="link" onClick={onToggle}>
          {open ? t('qbHideDetail') : t('qbShowDetail')}
        </button>
        <ReportIssue
          compact
          target={{
            qid: row.qid,
            bank: row.bank,
            version: row.version,
            source: row.source,
            competition: row.competition,
            question: row.question,
          }}
        />
        <span className="muted qb-qid">{row.qid}</span>
      </div>

      {open && (
        <div className="qb-detail">
          {row.choices.length > 0 && (
            <ol className="qb-choices">
              {row.choices.map((choice, i) => (
                <li key={i}>
                  <AutoMath html={choice} />
                </li>
              ))}
            </ol>
          )}
          <div className="qb-answer">
            <strong>{t('answer')}</strong> <AutoMath html={row.answer || '—'} />
          </div>
          <div className="qb-solution">
            <strong>{t('solutionLabel')}</strong>
            {row.solution ? (
              <AutoMath html={row.solution} className="solution" />
            ) : (
              <span className="muted"> {t('noSolution')}</span>
            )}
          </div>
          {tags.length > 0 && (
            <div className="qb-tags">
              <strong>{t('qbTags')}</strong>
              {tags.map((id) => (
                <span key={id} className="badge" title={id}>
                  {label(id)}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import type { Mastery, MasteryDomain } from '../lib/api'
import { Trophy } from '../components/icons'
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

/** Bar tint: comfortable, shaky, weak. Thresholds match the badge colours. */
function toneOf(value: number | null): '' | 'good' | 'mid' | 'low' {
  if (value === null) return ''
  if (value >= 70) return 'good'
  if (value >= 45) return 'mid'
  return 'low'
}

function barTone(value: number | null): string {
  const tone = toneOf(value)
  return tone ? `mst-bar ${tone}` : 'mst-bar'
}

function MasteryBar({ value }: { value: number | null }) {
  return (
    <span className={barTone(value)}>
      <span style={{ width: `${value ?? 0}%` }} />
    </span>
  )
}

function pick(lang: string, en: string | null, zh: string | null, fallback: string): string {
  return (lang === 'zh' ? zh || en : en || zh) || fallback
}

/** The figures for one area, optionally restricted to a single difficulty bucket. */
interface AreaValue {
  mastery: number | null
  accuracy: number | null
  n: number
}

function areaValue(domain: MasteryDomain, bucket: string | null): AreaValue {
  if (bucket === null) {
    return { mastery: domain.mastery, accuracy: domain.accuracy, n: domain.n }
  }
  let num = 0
  let den = 0
  let wins = 0
  for (const topic of domain.topics) {
    for (const cell of topic.cells) {
      if (cell.bucket !== bucket) continue
      num += (cell.mastery ?? 0) * cell.n
      den += cell.n
      wins += cell.wins
    }
  }
  if (!den) return { mastery: null, accuracy: null, n: 0 }
  return { mastery: Math.round(num / den), accuracy: wins / den, n: den }
}

interface RadarPoint {
  key: string
  label: string
  value: number | null
}

/**
 * Hand-rolled radar: eight axes, 0-100 rings. It is a chart, not an icon, so it
 * lives here rather than in components/icons.ts. Colours come from CSS tokens so
 * the dark theme follows along.
 */
function Radar({ points, center, caption }: { points: RadarPoint[]; center: string; caption: string }) {
  const size = 340
  const cx = size / 2
  const cy = size / 2
  const radius = 102
  const count = Math.max(1, points.length)
  const angleAt = (i: number) => (Math.PI * 2 * i) / count - Math.PI / 2
  const at = (i: number, r: number): [number, number] => [
    cx + Math.cos(angleAt(i)) * r,
    cy + Math.sin(angleAt(i)) * r,
  ]
  const ringPath = (fraction: number) =>
    points.map((_, i) => at(i, radius * fraction).join(',')).join(' ')

  const shape = points
    .map((point, i) => at(i, (Math.max(0, Math.min(100, point.value ?? 0)) / 100) * radius).join(','))
    .join(' ')

  return (
    <svg className="mst-radar" viewBox="-40 -18 420 376" role="img" aria-label={caption}>
      <title>{caption}</title>
      {[0.25, 0.5, 0.75, 1].map((fraction) => (
        <polygon key={fraction} className="mst-radar-ring" points={ringPath(fraction)} />
      ))}
      {points.map((point, i) => {
        const [x, y] = at(i, radius)
        return <line key={point.key} className="mst-radar-axis" x1={cx} y1={cy} x2={x} y2={y} />
      })}
      <polygon className="mst-radar-area" points={shape} />
      {points.map((point, i) => {
        const [x, y] = at(i, (Math.max(0, Math.min(100, point.value ?? 0)) / 100) * radius)
        return <circle key={point.key} className="mst-radar-dot" cx={x} cy={y} r={3} />
      })}
      {points.map((point, i) => {
        const [x, y] = at(i, radius + 18)
        const cos = Math.cos(angleAt(i))
        const anchor = Math.abs(cos) < 0.2 ? 'middle' : cos > 0 ? 'start' : 'end'
        return (
          <g key={`${point.key}-label`}>
            <text className={point.value === null ? 'mst-radar-label weak' : 'mst-radar-label'} x={x} y={y} textAnchor={anchor}>
              {point.label}
            </text>
            <text className="mst-radar-val" x={x} y={y + 13} textAnchor={anchor}>
              {point.value === null ? '–' : `${point.value}%`}
            </text>
          </g>
        )
      })}
      <text className="mst-radar-center" x={cx} y={cy + 6} textAnchor="middle">
        {center}
      </text>
    </svg>
  )
}

function DomainRow({ domain, bucket }: { domain: MasteryDomain; bucket: string | null }) {
  const { lang } = useI18n()
  const value = areaValue(domain, bucket)
  return (
    <div className="mst-row">
      <span className="mst-row-name">
        {pick(lang, domain.en, domain.zh, domain.id)}
        {domain.level !== null && <span className="muted"> L{domain.level.toFixed(1)}</span>}
      </span>
      <span className="mst-row-m">
        <MasteryBar value={value.mastery} />
        <span className="mst-row-pct">{value.mastery !== null ? `${value.mastery}%` : '–'}</span>
      </span>
      <span className="muted mst-row-num">
        {value.accuracy !== null ? `${Math.round(value.accuracy * 100)}%` : '–'}
      </span>
      <span className="muted mst-row-num">{value.n}</span>
    </div>
  )
}

/** Mastery page: one rating, then a radar of the first-level areas plus exact numbers. */
export function Stats() {
  const { t, lang } = useI18n()
  const [mastery, setMastery] = useState<Mastery | null>(null)
  const [stats, setStats] = useState<StatsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [bucket, setBucket] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    api
      .mastery()
      .then((d) => {
        if (alive) setMastery(d)
      })
      .catch((e: unknown) => {
        if (alive) setError(String(e))
      })
    api
      .stats()
      .then((d) => {
        if (alive) setStats(d as StatsData)
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])

  const radarPoints = useMemo<RadarPoint[]>(() => {
    if (!mastery) return []
    return mastery.domains.map((domain) => ({
      key: domain.id,
      label: pick(lang, domain.en, domain.zh, domain.id),
      value: areaValue(domain, bucket).mastery,
    }))
  }, [mastery, bucket, lang])

  const centerValue = useMemo(() => {
    if (!mastery) return '–'
    if (bucket === null) {
      const num = mastery.domains.reduce((sum, d) => sum + (d.mastery ?? 0) * d.n, 0)
      const den = mastery.domains.reduce((sum, d) => sum + d.n, 0)
      return den ? `${Math.round(num / den)}%` : '–'
    }
    const hit = mastery.buckets.find((b) => b.bucket === bucket)
    return hit && hit.mastery !== null ? `${hit.mastery}%` : '–'
  }, [mastery, bucket])

  if (error) {
    return (
      <section className="card">
        <p className="status err">{error.includes('401') ? t('mstLogin') : `API error: ${error}`}</p>
      </section>
    )
  }
  if (!mastery) {
    return (
      <section className="card">
        <p className="muted">{t('loading')}</p>
      </section>
    )
  }

  const rating = mastery.rating
  const empty = mastery.totals.answered === 0
  const bucketLabel = bucket === null ? t('mstAll') : `L${bucket}`

  return (
    <>
      <section className="card mst-hero">
        <div className="mst-hero-main">
          <div className="mst-rating">
            <span className="mst-rating-num">{rating ? rating.level.toFixed(2) : '–'}</span>
            <span className="mst-rating-cap">{t('mstLevel')}</span>
          </div>
          <div className="mst-rating-side">
            <div className="mst-rating-label">
              <Trophy size={16} aria-hidden="true" /> {t('mstRating')}
            </div>
            {rating ? (
              <>
                <div className={`mst-band ${rating.band ?? ''}`}>
                  {t(rating.band === 'easy' ? 'easy' : rating.band === 'hard' ? 'hard' : 'medium')}
                </div>
                <div className="muted">
                  {t('mstConfidence')} {rating.ci[0].toFixed(1)}–{rating.ci[1].toFixed(1)} · {rating.n} {t('mstQs')}
                </div>
              </>
            ) : (
              <div className="muted">{t('mstNoLevel')}</div>
            )}
          </div>
        </div>
        <div className="mst-figures">
          <div>
            <span className="mst-fig">{mastery.totals.answered}</span>
            <span className="muted">{t('mstQs')}</span>
          </div>
          <div>
            <span className="mst-fig">
              {mastery.totals.accuracy !== null ? `${Math.round(mastery.totals.accuracy * 100)}%` : '–'}
            </span>
            <span className="muted">{t('mstAccuracy')}</span>
          </div>
          <div>
            <span className="mst-fig">{mastery.totals.attempts}</span>
            <span className="muted">{t('mstTests')}</span>
          </div>
        </div>
        <p className="mst-note">
          {t('mstScale')} · {t('mstDecayNote')}
          {mastery.totals.last_at ? ` · ${t('mstLastAnswered')} ${mastery.totals.last_at}` : ''}
        </p>
      </section>

      {empty ? (
        <section className="card">
          <p className="muted">{t('mstEmpty')}</p>
        </section>
      ) : (
        <>
          <h2 className="section-title">{t('mstByArea')}</h2>
          <section className="card mst-panel">
            <div className="mst-panel-left">
              <div className="mst-seg" role="group" aria-label={t('mstFilter')}>
                <button
                  type="button"
                  className={bucket === null ? 'mst-seg-btn on' : 'mst-seg-btn'}
                  onClick={() => setBucket(null)}
                >
                  {t('mstAll')}
                </button>
                {mastery.buckets.map((b) => (
                  <button
                    type="button"
                    key={b.bucket}
                    className={bucket === b.bucket ? 'mst-seg-btn on' : 'mst-seg-btn'}
                    onClick={() => setBucket(b.bucket)}
                  >
                    L{b.bucket}
                    <span className="mst-seg-pct">{b.mastery !== null ? `${b.mastery}%` : '–'}</span>
                  </button>
                ))}
              </div>
              <Radar points={radarPoints} center={centerValue} caption={t('mstRadarCap')} />
              <p className="mst-note mst-radar-note">
                {t('mstFilter')}: {bucketLabel}
              </p>
            </div>
            <div className="mst-panel-right">
              <div className="mst-row mst-row-head">
                <span>{t('mstArea')}</span>
                <span>{t('mstMastery')}</span>
                <span>{t('mstAccuracy')}</span>
                <span>{t('mstQs')}</span>
              </div>
              {mastery.domains.map((domain) => (
                <DomainRow domain={domain} bucket={bucket} key={domain.id} />
              ))}
              {radarPoints.every((p) => p.value === null) && (
                <p className="muted mst-panel-empty">{t('mstNoData')}</p>
              )}
            </div>
          </section>

          <div className="mst-two">
            <section className="card">
              <h3 style={{ marginBottom: 10 }}>{t('mstWeakest')}</h3>
              {mastery.weakest.length ? (
                <ul className="mst-weak">
                  {mastery.weakest.map((spot) => (
                    <li key={`${spot.topic}-${spot.bucket}`}>
                      <span className="mst-wname">
                        {pick(lang, spot.en, spot.zh, spot.topic)}
                        <span className="muted"> · L{spot.bucket}</span>
                      </span>
                      <span className={`mst-wpct ${toneOf(spot.mastery)}`}>
                        {spot.mastery !== null ? `${spot.mastery}%` : '–'}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">{t('mstNoLevel')}</p>
              )}
            </section>

            <section className="card">
              <h3 style={{ marginBottom: 10 }}>{t('mstByDifficulty')}</h3>
              <ul className="mst-buckets">
                {mastery.buckets.map((b) => (
                  <li key={b.bucket}>
                    <span className="mst-bname">L{b.bucket}</span>
                    <MasteryBar value={b.mastery} />
                    <span className="mst-bpct">
                      {b.mastery !== null ? `${b.mastery}%` : '–'}
                      <span className="muted"> ({b.n})</span>
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}

      {stats && (
        <details className="card mst-legacy">
          <summary>{t('mstLegacy')}</summary>
          <div className="mst-legacy-body">
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
        </details>
      )}
    </>
  )
}

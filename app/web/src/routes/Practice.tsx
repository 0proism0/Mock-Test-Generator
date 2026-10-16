import { useCallback, useEffect, useRef, useState } from 'react'
import { AutoMath } from '../components/AutoMath'
import { api, type PracticeLevelStats, type PracticeStats } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

type Level = 'easy' | 'medium' | 'hard'

interface DrQ {
  q: string // may contain $...$ LaTeX
  v: number
  disp?: string // display form for fractions
  frac?: boolean
}

interface RunResult {
  pct: number
  time_s: number
  correct: number
  total: number
  newBest: boolean
  rec: PracticeLevelStats
}

const N_Q = 10
const LEVELS: Level[] = ['easy', 'medium', 'hard']

const rnd = (a: number, b: number) => a + Math.floor(Math.random() * (b - a + 1))
const gcd = (a: number, b: number): number => (b ? gcd(b, a % b) : a)

function genAddSub(lv: Level): DrQ {
  const [lo, hi] = lv === 'easy' ? [2, 20] : lv === 'medium' ? [15, 99] : [100, 999]
  const a = rnd(lo, hi)
  const b = rnd(lo, hi)
  if (Math.random() < 0.5) return { q: `${a} + ${b} = ?`, v: a + b }
  const [hi2, lo2] = a >= b ? [a, b] : [b, a]
  return { q: `${hi2} − ${lo2} = ?`, v: hi2 - lo2 }
}

function genMult(lv: Level): DrQ {
  let a: number, b: number
  if (lv === 'easy') {
    a = rnd(2, 9)
    b = rnd(2, 9)
  } else if (lv === 'medium') {
    a = rnd(3, 12)
    b = rnd(3, 12)
  } else {
    a = rnd(13, 49)
    b = rnd(3, 9)
  }
  return { q: `${a} × ${b} = ?`, v: a * b }
}

function genDiv(lv: Level): DrQ {
  const [dl, dh, ql, qh] =
    lv === 'easy' ? [2, 9, 2, 9] : lv === 'medium' ? [3, 12, 4, 15] : [6, 15, 11, 30]
  const d = rnd(dl, dh)
  const qq = rnd(ql, qh)
  return { q: `${d * qq} ÷ ${d} = ?`, v: qq }
}

function genFrac(lv: Level): DrQ {
  let a: number, b: number, c: number, d: number, op: string
  if (lv === 'hard') {
    op = '×'
    a = rnd(2, 9)
    b = rnd(3, 10)
    c = rnd(2, 9)
    d = rnd(3, 10)
  } else {
    op = Math.random() < 0.5 ? '+' : '−'
    b = rnd(lv === 'easy' ? 2 : 3, lv === 'easy' ? 6 : 9)
    d = lv === 'easy' ? b : rnd(3, 9)
    a = rnd(1, 9)
    c = rnd(1, 9)
    if (op === '−' && a * d < c * b) {
      ;[a, c] = [c, a]
      ;[b, d] = [d, b]
    }
  }
  const nn = op === '+' ? a * d + c * b : op === '−' ? a * d - c * b : a * c
  const dd = b * d
  const g = gcd(Math.abs(nn), dd)
  const sn = nn / g
  const sd = dd / g
  return {
    q: `$\\frac{${a}}{${b}} ${op} \\frac{${c}}{${d}} = ?$`,
    v: sn / sd,
    disp: sd === 1 ? String(sn) : `${sn}/${sd}`,
    frac: true,
  }
}

function genPct(lv: Level): DrQ {
  if (lv === 'hard') {
    const p = rnd(2, 19) * 5
    const y = rnd(2, 12) * (100 / gcd(p, 100))
    return { q: `${(p * y) / 100} is what % of ${y}?`, v: p }
  }
  if (lv === 'easy') {
    const p = [10, 20, 25, 50][rnd(0, 3)]
    const y = rnd(2, 20) * (100 / p)
    return { q: `${p}% of ${y} = ?`, v: (p * y) / 100 }
  }
  const p = rnd(2, 19) * 5
  const y = rnd(2, 12) * (100 / gcd(p, 100))
  return { q: `${p}% of ${y} = ?`, v: (p * y) / 100 }
}

function genPow(lv: Level): DrQ {
  if (lv === 'easy') {
    const a = rnd(2, 15)
    return { q: `${a}² = ?`, v: a * a }
  }
  if (lv === 'medium') {
    if (Math.random() < 0.5) {
      const a = rnd(2, 12)
      return { q: `${a}³ = ?`, v: a ** 3 }
    }
    const a = rnd(13, 25)
    return { q: `${a}² = ?`, v: a * a }
  }
  const k = rnd(0, 2)
  if (k === 0) {
    const a = rnd(11, 40)
    return { q: `√${a * a} = ?`, v: a }
  }
  if (k === 1) {
    const n = rnd(4, 10)
    return { q: `2^${n} = ?`, v: 2 ** n }
  }
  const a = rnd(2, 5)
  const b = rnd(2, 4)
  return { q: `${a}^${b} = ?`, v: a ** b }
}

// new drill: linear equations
function genEq(lv: Level): DrQ {
  if (lv === 'easy') {
    const x = rnd(1, 20)
    const a = rnd(2, 30)
    return { q: `Solve for $x$: $x + ${a} = ${x + a}$`, v: x }
  }
  if (lv === 'medium') {
    const x = rnd(2, 15)
    const a = rnd(2, 9)
    const b = rnd(1, 20)
    return { q: `Solve for $x$: $${a}x + ${b} = ${a * x + b}$`, v: x }
  }
  // hard: ax + b = cx + d, integer positive solution
  let x = 0
  let a = 0
  let c = 0
  let b = 0
  do {
    x = rnd(2, 12)
    a = rnd(2, 9)
    c = rnd(1, a - 1)
    b = rnd(1, 20)
  } while (c * x + b - a * x < 1)
  const d = c * x + b - a * x
  return { q: `Solve for $x$: $${a}x + ${b} = ${c}x + ${d}$`, v: x }
}

// new drill: gcd & lcm
function genGcdLcm(lv: Level): DrQ {
  if (lv === 'easy') {
    const g = rnd(2, 9)
    const a = g * rnd(2, 9)
    const b = g * rnd(2, 9)
    return { q: `GCD of ${a} and ${b} = ?`, v: gcd(a, b) }
  }
  if (lv === 'medium') {
    const g = rnd(2, 6)
    const a = g * rnd(2, 7)
    const b = g * rnd(2, 7)
    return { q: `LCM of ${a} and ${b} = ?`, v: (a * b) / gcd(a, b) }
  }
  if (Math.random() < 0.5) {
    const a = rnd(12, 60)
    const b = rnd(12, 60)
    const c = rnd(12, 60)
    return { q: `GCD of ${a}, ${b} and ${c} = ?`, v: gcd(gcd(a, b), c) }
  }
  const g = rnd(2, 8)
  const a = g * rnd(3, 9)
  const b = g * rnd(3, 9)
  return { q: `LCM of ${a} and ${b} = ?`, v: (a * b) / gcd(a, b) }
}

const DRILLS: Record<string, { name: string; desc: string; gen: (lv: Level) => DrQ }> = {
  addsub: { name: 'drAddSub', desc: 'drAddSubDesc', gen: genAddSub },
  mult: { name: 'drMult', desc: 'drMultDesc', gen: genMult },
  div: { name: 'drDiv', desc: 'drDivDesc', gen: genDiv },
  frac: { name: 'drFrac', desc: 'drFracDesc', gen: genFrac },
  pct: { name: 'drPct', desc: 'drPctDesc', gen: genPct },
  pow: { name: 'drPow', desc: 'drPowDesc', gen: genPow },
  eq: { name: 'drEq', desc: 'drEqDesc', gen: genEq },
  gcdlcm: { name: 'drGcdLcm', desc: 'drGcdLcmDesc', gen: genGcdLcm },
}

function drMatch(given: string, rec: DrQ): boolean {
  const g = given.trim().replace(/\s+/g, '').replace(/，/g, ',').toLowerCase()
  if (rec.frac) {
    const m = g.match(/^(-?\d+)\/(-?\d+)$/)
    if (m) return Math.abs(parseInt(m[1], 10) / parseInt(m[2], 10) - rec.v) < 1e-9
    if (/^-?\d+$/.test(g)) return Math.abs(parseInt(g, 10) - rec.v) < 1e-9
    return false
  }
  const v = parseFloat(g.replace(',', '.'))
  return Number.isFinite(v) && Math.abs(v - rec.v) < 1e-9
}

function fmtTime(s: number): string {
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

function loadLocal(): PracticeStats {
  try {
    return JSON.parse(localStorage.getItem('mt_practice') || '{}') as PracticeStats
  } catch {
    return {}
  }
}

// ---------- drill runner ----------

function Runner({
  drill,
  level,
  onDone,
  onExit,
}: {
  drill: string
  level: Level
  onDone: (r: RunResult) => void
  onExit: () => void
}) {
  const { t } = useI18n()
  const [qs] = useState<DrQ[]>(() => Array.from({ length: N_Q }, () => DRILLS[drill].gen(level)))
  const [i, setI] = useState(0)
  const [correct, setCorrect] = useState(0)
  const [fb, setFb] = useState<{ ok: boolean; ans: string } | null>(null)
  const [value, setValue] = useState('')
  const [t0] = useState(() => Date.now())
  const [secs, setSecs] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const nextRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const tmr = setInterval(() => setSecs(Math.floor((Date.now() - t0) / 1000)), 500)
    return () => clearInterval(tmr)
  }, [t0])

  useEffect(() => {
    if (!fb) inputRef.current?.focus()
    else if (!fb.ok) nextRef.current?.focus()
  }, [i, fb])

  const next = useCallback(() => {
    setFb(null)
    setValue('')
    setI((n) => {
      if (n + 1 >= N_Q) return n
      return n + 1
    })
  }, [])

  function finish(correctCount: number) {
    const time_s = (Date.now() - t0) / 1000
    onDone({
      pct: Math.round((correctCount / N_Q) * 100),
      time_s,
      correct: correctCount,
      total: N_Q,
      newBest: false,
      rec: { best_pct: 0, best_time: null, sessions: 0, streak: 0 },
    })
  }

  function submit() {
    if (fb) return
    const val = value.trim()
    if (!val) return
    const q = qs[i]
    const ok = drMatch(val, q)
    const newCorrect = correct + (ok ? 1 : 0)
    if (ok) setCorrect(newCorrect)
    setFb({ ok, ans: q.frac && q.disp ? q.disp : String(q.v) })
    if (ok) {
      if (last) setTimeout(() => finish(newCorrect), 700)
      else setTimeout(next, 700)
    }
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key !== 'Enter') return
    e.preventDefault()
    if (fb && !fb.ok) {
      if (last) finish(correct)
      else next()
    } else submit()
  }

  const q = qs[i]
  const last = i + 1 >= N_Q
  return (
    <section className="card dr-run">
      <div className="dr-meta">
        <span>
          {t(DRILLS[drill].name)} · {t(level)}
        </span>
        <span>
          {i + 1} / {N_Q} · ✓ {correct} · {fmtTime(secs)}
        </span>
      </div>
      <div className="dr-q">
        <AutoMath html={q.q} />
      </div>
      <div className="dr-fb" aria-live="polite">
        {fb &&
          (fb.ok ? (
            <span className="dr-ok">{t('drCorrect')}</span>
          ) : (
            <>
              <span className="dr-bad">{t('drWrong', fb.ans)}</span>{' '}
              <button
                ref={nextRef}
                type="button"
                className="btn sm"
                onClick={() => (last ? finish(correct) : next())}
              >
                {t('drNext')}
              </button>
            </>
          ))}
      </div>
      <input
        ref={inputRef}
        value={value}
        disabled={!!fb}
        placeholder={t('drTypeAnswer')}
        className="dr-input"
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKey}
      />
      <div className="dr-exit">
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => {
            if (!fb || window.confirm(t('drExitConfirm'))) onExit()
          }}
        >
          {t('exit')}
        </button>
      </div>
    </section>
  )
}

// ---------- main practice view ----------

export function Practice() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [stats, setStats] = useState<PracticeStats | null>(null)
  const [run, setRun] = useState<{ drill: string; level: Level } | null>(null)
  const [result, setResult] = useState<(RunResult & { drill: string; level: Level }) | null>(null)

  useEffect(() => {
    if (!user) {
      setStats(loadLocal())
      return
    }
    api
      .practice()
      .then((d) => setStats('guest' in d ? {} : d))
      .catch(() => setStats(loadLocal()))
  }, [user])

  function saveStats(drill: string, level: Level, r: Omit<RunResult, 'newBest' | 'rec'>) {
    const cur = stats ?? {}
    const prev: PracticeLevelStats = cur[drill]?.[level] ?? {
      best_pct: 0,
      best_time: null,
      sessions: 0,
      streak: 0,
    }
    const rec: PracticeLevelStats = {
      best_pct: Math.max(prev.best_pct, r.pct),
      best_time: prev.best_time,
      sessions: prev.sessions + 1,
      streak: r.pct >= 80 ? prev.streak + 1 : 0,
    }
    if (r.pct >= 100 && (prev.best_time == null || r.time_s < prev.best_time)) {
      rec.best_time = r.time_s
    }
    const newBest = r.pct > prev.best_pct || rec.best_time !== prev.best_time
    const next: PracticeStats = { ...cur, [drill]: { ...cur[drill], [level]: rec } }
    setStats(next)
    localStorage.setItem('mt_practice', JSON.stringify(next))
    if (user) {
      api
        .practiceSave({ drill, level, pct: r.pct, time_s: r.time_s, correct: r.correct, total: r.total })
        .then((d) => setStats(d.stats))
        .catch(() => {})
    }
    setResult({ ...r, newBest, rec, drill, level })
    setRun(null)
  }

  if (run) {
    return (
      <Runner
        drill={run.drill}
        level={run.level}
        onExit={() => setRun(null)}
        onDone={(r) => saveStats(run.drill, run.level, r)}
      />
    )
  }

  if (result) {
    const { drill, level } = result
    return (
      <section className="card dr-summary">
        <h3>
          {t(DRILLS[drill].name)} · {t(level)}
        </h3>
        <div className="dr-emoji">{result.pct >= 80 ? '🎉' : result.pct >= 50 ? '💪' : '📚'}</div>
        <div className="dr-scoreline">
          {t('drScore')}: <b>
            {result.correct}/{result.total}
          </b>{' '}
          ({result.pct}%)
        </div>
        <p className="meta">
          {t('drTime')}: {fmtTime(Math.round(result.time_s))} · {t('drBest')}: {result.rec.best_pct}% · ⏱{' '}
          {result.rec.best_time != null ? fmtTime(Math.round(result.rec.best_time)) : '—'} · {t('drStreak')}{' '}
          {result.rec.streak}
        </p>
        {result.newBest && <p className="dr-newbest">{t('drNewBest')}</p>}
        <div className="dr-actions">
          <button type="button" className="btn" onClick={() => { setResult(null); setRun({ drill, level }) }}>
            {t('drAgain')}
          </button>
          <button type="button" className="btn ghost" onClick={() => setResult(null)}>
            {t('drBack')}
          </button>
        </div>
      </section>
    )
  }

  return (
    <section className="card">
      <h3>{t('tabPractice')}</h3>
      <p className="muted">{t('drDesc')}</p>
      {!stats ? (
        <p className="muted">{t('loading')}</p>
      ) : (
        <div className="gen-grid">
          {Object.entries(DRILLS).map(([key, d]) => (
            <div key={key} className="card compact">
              <h3>{t(d.name)}</h3>
              <p className="muted">{t(d.desc)}</p>
              <div className="dr-levels">
                {LEVELS.map((lv) => {
                  const b = stats[key]?.[lv]
                  let lbl = t(lv)
                  if (b) {
                    lbl += ` · ${b.best_pct}%`
                    if (b.best_time != null) lbl += ` · ${fmtTime(Math.round(b.best_time))}`
                  }
                  return (
                    <button key={lv} type="button" className="btn sm" onClick={() => setRun({ drill: key, level: lv })}>
                      {lbl}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

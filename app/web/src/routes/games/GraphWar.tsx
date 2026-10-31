import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Flame, Grid, RotateCcw } from '../../components/icons'
import { useI18n } from '../../lib/i18n'
import { useTheme } from '../../lib/theme'
import { GW_H, GW_W, compile, cssVar, drawCurve, drawGrid, gwXY, plotColor, withAlpha } from './engine'
import { StatusLine } from './StatusLine'

interface GPoint {
  x: number
  y: number
  hit: boolean
}

interface GwState {
  yours: GPoint[]
  enemys: GPoint[]
  round: number
  you: number
  ai: number
  ans: string
  over: boolean
  msg: string
  tone: 'info' | 'ok' | 'err'
  grid: boolean
  firing: boolean
}

/** Random 5v5 points, with round i's pair guaranteed to differ in x (so a line exists). */
function initGw(msg: string): GwState {
  const yours: GPoint[] = []
  const enemys: GPoint[] = []
  const used = new Set<string>()
  const mk = (arr: GPoint[]) => {
    let guard = 0
    while (arr.length < 5 && guard++ < 500) {
      const x = Math.round((Math.random() * 16 - 8) * 2) / 2
      const y = Math.round((Math.random() * 16 - 8) * 2) / 2
      const k = `${x},${y}`
      if (used.has(k)) continue
      used.add(k)
      arr.push({ x, y, hit: false })
    }
  }
  mk(yours)
  mk(enemys)
  for (let i = 0; i < 5; i++) {
    if (yours[i].x === enemys[i].x) {
      for (let j = 0; j < 5; j++) {
        if (yours[i].x !== enemys[j].x && yours[j].x !== enemys[i].x) {
          const tmp = enemys[i]
          enemys[i] = enemys[j]
          enemys[j] = tmp
          break
        }
      }
    }
  }
  return {
    yours,
    enemys,
    round: 1,
    you: 0,
    ai: 0,
    ans: '',
    over: false,
    msg,
    tone: 'info',
    grid: true,
    firing: false,
  }
}

/** Graph War: fire a line through your point #N and the enemy's point #N. */
export function GraphWar({ onBack }: { onBack: () => void }) {
  const { t, tip } = useI18n()
  const { theme } = useTheme()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const timerRef = useRef<number | null>(null)
  const [s, setS] = useState<GwState>(() => initGw(''))

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current)
    }
  }, [])

  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    if (!ctx) return
    // Deferred one frame so the provider's <html data-theme> stamp has landed before the
    // tokens are read — child effects flush before the provider's own effect.
    const raf = requestAnimationFrame(() => {
      drawGrid(ctx, GW_W, GW_H, s.grid)
      if (s.ans) {
        try {
          drawCurve(ctx, compile(s.ans), withAlpha(plotColor('you'), 0.8))
        } catch {
          /* invalid while typing */
        }
      }
      // Ring and number are both knocked out to the plot background instead of hard-coded
      // white: in light mode that is exactly what the old #fff did, and in dark mode it keeps
      // the 10–13px digit legible on the lighter dark-mode dots (white on #6ba4ff is ~2.5:1;
      // the plot background on it is ~7:1).
      const knockout = cssVar('--plot-bg', '#ffffff')
      for (let i = 1; i <= 5; i++) {
        for (const side of ['you', 'ai'] as const) {
          const p = (side === 'you' ? s.yours : s.enemys)[i - 1]
          if (!p || p.hit) continue
          const isNow = i === s.round && !s.over
          const [x, y] = gwXY(p.x, p.y)
          ctx.globalAlpha = isNow ? 1 : 0.45
          ctx.fillStyle = plotColor(side)
          ctx.strokeStyle = knockout
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.arc(x, y, isNow ? 12 : 9, 0, Math.PI * 2)
          ctx.fill()
          ctx.stroke()
          ctx.fillStyle = knockout
          ctx.font = `bold ${isNow ? 13 : 10}px sans-serif`
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText(String(i), x, y + 0.5)
          ctx.globalAlpha = 1
        }
      }
    })
    return () => cancelAnimationFrame(raf)
  }, [s, theme])

  function fire() {
    if (s.over || s.firing) return
    const r = Math.min(s.round, 5)
    let fn: (x: number) => number
    try {
      fn = compile(s.ans)
    } catch {
      setS((prev) => ({ ...prev, tone: 'err', msg: t('gFcBadExpr') }))
      return
    }
    const a = s.yours[r - 1]
    const b = s.enemys[r - 1]
    const ok = Math.abs(fn(a.x) - a.y) <= 0.26 && Math.abs(fn(b.x) - b.y) <= 0.26
    setS((prev) => ({
      ...prev,
      enemys: ok ? prev.enemys.map((p, i) => (i === r - 1 ? { ...p, hit: true } : p)) : prev.enemys,
      you: prev.you + (ok ? 100 : 0),
      firing: true,
      tone: ok ? 'ok' : 'info',
      msg: ok ? t('gGwHit', r) : t('gGwMiss', r),
    }))
    timerRef.current = window.setTimeout(() => {
      setS((prev) => {
        if (prev.over) return prev
        let yours = prev.yours
        let ai = prev.ai
        let msg = prev.msg
        if (Math.random() < 0.65) {
          yours = prev.yours.map((p, i) => (i === r - 1 ? { ...p, hit: true } : p))
          ai += 100
          msg += ` · ${t('gAI')} +100`
        } else {
          msg += ` · ${t('gAI')} +0`
        }
        const round = prev.round + 1
        if (round > 5) {
          const you = prev.you
          const final = (you > ai ? tip('gYouWin') : ai > you ? tip('gAiWin') : t('gRoundTie')) + `  (${you} : ${ai})`
          return {
            ...prev,
            yours,
            ai,
            round,
            over: true,
            firing: false,
            tone: you > ai ? 'ok' : ai > you ? 'err' : 'info',
            msg: final,
          }
        }
        return { ...prev, yours, ai, round, firing: false, ans: '', msg: msg + ` — ${t('gGwNext', round)}` }
      })
    }, 900)
  }

  return (
    <div className="card">
      <div className="fr-req" style={{ borderTop: 'none' }}>
        <h3>{tip('gGraph')}</h3>
        <button className="btn sm ghost" type="button" onClick={onBack}>
          <ArrowLeft size={14} /> {tip('gBack')}
        </button>
      </div>
      <div style={{ fontSize: 14.5, marginBottom: 8 }}>
        {t('gGwRound', Math.min(s.round, 5))} · <b style={{ color: 'var(--plot-you)' }}>{t('gYou')}: {s.you}</b> ·{' '}
        <b style={{ color: 'var(--plot-ai)' }}>{t('gAI')}: {s.ai}</b>
      </div>
      <div className="gw-wrap">
        <div className="gw-canvas-box">
          <canvas ref={canvasRef} width={GW_W} height={GW_H} style={{ maxWidth: '100%' }} />
        </div>
        <div className="gw-ctl">
          <StatusLine tone={s.tone}>{s.msg}</StatusLine>
          <div style={{ fontSize: 13.5, color: 'var(--ink-2)', marginBottom: 6 }}>{t('gGwTask')}</div>
          <label>f(x) =</label>
          <input
            className="gw-input"
            type="text"
            placeholder="e.g. 0.5x + 3"
            value={s.ans}
            disabled={s.over || s.firing}
            onChange={(e) => setS((prev) => ({ ...prev, ans: e.target.value }))}
          />
          <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn" type="button" disabled={s.over || s.firing} onClick={fire}>
              <Flame size={13} /> {tip('gFire')}
            </button>
            <button className="btn sm ghost" type="button" onClick={() => setS((prev) => ({ ...prev, grid: !prev.grid }))}>
              <Grid size={13} /> {t('gGrid')}
            </button>
            <button className="btn sm ghost" type="button" onClick={() => setS(initGw(t('gGwYourTurn')))}>
              <RotateCcw size={13} /> {t('gPlay')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

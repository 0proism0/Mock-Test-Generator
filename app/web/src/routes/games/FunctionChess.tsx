import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Grid, RotateCcw } from '../../components/icons'
import { useI18n } from '../../lib/i18n'
import { useTheme } from '../../lib/theme'
import { GW_H, GW_W, compile, cssVar, drawCurve, drawGrid, gwXY, plotColor, withAlpha } from './engine'
import { StatusLine } from './StatusLine'

interface Pt {
  x: number
  y: number
  shown: boolean
}

const BEST_KEY = 'mt_fc_best'

/** Hidden "nice" polynomial the enemy uses to place points (legacy fcPoly). */
function makePoly(round: number): number[] {
  const d = Math.min(round - 1, 4)
  const coef: number[] = []
  for (let i = 0; i <= d; i++) coef.push(Math.floor(Math.random() * 9) - 4)
  if (coef[d] === 0) coef[d] = 1 + Math.floor(Math.random() * 3)
  return coef
}

function evalPoly(coef: number[], x: number): number {
  return coef.reduce((s, c, i) => s + c * Math.pow(x, i), 0)
}

function polyStr(coef: number[]): string {
  const T = ['', 'x', 'x^2', 'x^3', 'x^4']
  const parts: string[] = []
  for (let i = coef.length - 1; i >= 0; i--) {
    const c = coef[i]
    if (!c) continue
    const sign = c < 0 ? '−' : '+'
    const a = Math.abs(c)
    const term = i === 0 ? String(a) : a === 1 ? T[i] : a + T[i]
    parts.push((parts.length ? sign : c < 0 ? '−' : '') + term)
  }
  return parts.join(' ') || '0'
}

/** Function Chess: the enemy reveals points one by one; fit a function through all of them. */
export function FunctionChess({ onBack }: { onBack: () => void }) {
  const { t, tip } = useI18n()
  const { theme } = useTheme()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const timerRef = useRef<number | null>(null)

  const [round, setRound] = useState(1)
  const [best, setBest] = useState(() => Number(localStorage.getItem(BEST_KEY) || 0))
  const [pts, setPts] = useState<Pt[]>([])
  const [ans, setAns] = useState('')
  const [poly, setPoly] = useState('')
  const [placing, setPlacing] = useState(true)
  const [over, setOver] = useState(false)
  const [tone, setTone] = useState<'info' | 'ok' | 'err'>('info')
  const [msg, setMsg] = useState('')
  const [grid, setGrid] = useState(true)

  function revealAll(n: number) {
    if (timerRef.current) window.clearTimeout(timerRef.current)
    let i = 0
    const step = () => {
      if (i < n) {
        const idx = i++
        setPts((prev) => prev.map((p, j) => (j === idx ? { ...p, shown: true } : p)))
        timerRef.current = window.setTimeout(step, 450)
      } else {
        setPlacing(false)
        setTone('info')
        setMsg(t('gFcYourMove'))
      }
    }
    timerRef.current = window.setTimeout(step, 400)
  }

  function deal(currentRound: number) {
    for (let attempt = 0; attempt < 60; attempt++) {
      const coef = makePoly(currentRound)
      const chosen: Pt[] = []
      const used = new Set<number>()
      let guard = 0
      while (chosen.length < currentRound && guard++ < 500) {
        const x = Math.round((Math.random() * 16 - 8) * 2) / 2
        if (used.has(x)) continue
        const y = Math.round(evalPoly(coef, x) * 2) / 2
        if (y < -9 || y > 9) continue
        used.add(x)
        chosen.push({ x, y, shown: false })
      }
      if (chosen.length < currentRound) continue
      setPts(chosen)
      setPoly(polyStr(coef))
      setAns('')
      setPlacing(true)
      setTone('info')
      setMsg(t('gFcPlacing', currentRound))
      revealAll(chosen.length)
      return
    }
  }

  function startGame() {
    if (timerRef.current) window.clearTimeout(timerRef.current)
    setRound(1)
    setOver(false)
    setBest(Number(localStorage.getItem(BEST_KEY) || 0))
    deal(1)
  }

  useEffect(() => {
    startGame()
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current)
    }
    // start once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    if (!ctx) return
    // Deferred one frame so the provider's <html data-theme> stamp has landed before the
    // tokens are read — child effects flush before the provider's own effect.
    const raf = requestAnimationFrame(() => {
      drawGrid(ctx, GW_W, GW_H, grid)
      if (ans) {
        try {
          drawCurve(ctx, compile(ans), withAlpha(plotColor('you'), 0.8))
        } catch {
          /* invalid while typing */
        }
      }
      // The ring is knocked out to the plot background rather than hard-coded white: on the
      // light plot it was always white-on-white, and in dark mode a white ring would halo
      // the dot. This way the dot sits cleanly on both.
      const ring = cssVar('--plot-bg', '#ffffff')
      for (const p of pts) {
        if (!p.shown) continue
        const [x, y] = gwXY(p.x, p.y)
        ctx.fillStyle = plotColor('ai')
        ctx.strokeStyle = ring
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.arc(x, y, 8, 0, Math.PI * 2)
        ctx.fill()
        ctx.stroke()
      }
    })
    return () => cancelAnimationFrame(raf)
  }, [pts, ans, grid, theme])

  function submit() {
    if (over || placing) return
    let fn: (x: number) => number
    try {
      fn = compile(ans)
    } catch {
      setTone('err')
      setMsg(t('gFcBadExpr'))
      return
    }
    const ok = pts.every((p) => Math.abs(fn(p.x) - p.y) <= 0.26)
    if (ok) {
      const cleared = round
      const nb = Math.max(best, cleared)
      setBest(nb)
      localStorage.setItem(BEST_KEY, String(nb))
      const nr = round + 1
      setRound(nr)
      setTone('ok')
      setMsg(t('gFcCleared', cleared))
      timerRef.current = window.setTimeout(() => deal(nr), 900)
    } else {
      setOver(true)
      setTone('err')
      setMsg(t('gFcWrong', poly))
    }
  }

  function giveUp() {
    if (over) return
    setOver(true)
    setTone('err')
    setMsg(t('gFcWrong', poly))
  }

  return (
    <div className="card">
      <div className="fr-req" style={{ borderTop: 'none' }}>
        <h3>{tip('gChess')}</h3>
        <button className="btn sm ghost" type="button" onClick={onBack}>
          <ArrowLeft size={14} /> {tip('gBack')}
        </button>
      </div>
      <div style={{ fontSize: 14.5, marginBottom: 8 }}>
        {t('gFcRound', round)} · {t('gFcBest', best)}
      </div>
      <div className="gw-wrap">
        <div className="gw-canvas-box">
          <canvas ref={canvasRef} width={GW_W} height={GW_H} style={{ maxWidth: '100%' }} />
        </div>
        <div className="gw-ctl">
          <StatusLine tone={tone}>{msg}</StatusLine>
          <label>f(x) =</label>
          <input
            className="gw-input"
            type="text"
            placeholder="e.g. x^2 - 2x + 1"
            value={ans}
            disabled={over || placing}
            onChange={(e) => setAns(e.target.value)}
          />
          <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 4 }}>{t('gFcHint')}</div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn" type="button" disabled={over || placing} onClick={submit}>
              {t('gFcSubmit')}
            </button>
            <button className="btn sm ghost" type="button" disabled={over || placing} onClick={giveUp}>
              {t('gFcGiveUp')}
            </button>
            <button className="btn sm ghost" type="button" onClick={() => setGrid((g) => !g)}>
              <Grid size={13} /> {t('gGrid')}
            </button>
            {over && (
              <button className="btn sm" type="button" onClick={startGame}>
                <RotateCcw size={13} /> {t('gPlay')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

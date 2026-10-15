/** Shared canvas/expression helpers for the Games tab (legacy evCompile + Graph War grid). */

export const GW_W = 920
export const GW_H = 700

/** World (math) coords → canvas pixels. */
export function gwXY(x: number, y: number): [number, number] {
  return [GW_W / 2 + (x * (GW_W / 2 - 24)) / 10, GW_H / 2 - (y * (GW_H / 2 - 24)) / 10]
}

/**
 * Compile a user expression like `2x^2 - 3x + 1` into f(x).
 * Legacy evCompile(): only digits/x/operators are allowed; implicit multiplication is
 * inserted; the result is NaN outside the real numbers.
 */
export function compile(input: string): (x: number) => number {
  let s = String(input || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/−/g, '-')
    .replace(/×/g, '*')
    .replace(/÷/g, '/')
    .replace(/\^/g, '**')
  if (!s || !/^[0-9x+\-*/().]*$/.test(s)) throw new Error('bad expression')
  s = s
    .replace(/(\d)x/g, '$1*x')
    .replace(/(\d)\(/g, '$1*(')
    .replace(/x\(/g, 'x*(')
    .replace(/\)(?=[0-9x(])/g, ')*')
  // eslint-disable-next-line no-new-func
  const fn = new Function('x', 'return (' + s + ');') as (x: number) => unknown
  return (x: number) => {
    const v = fn(x)
    return typeof v === 'number' && isFinite(v) ? v : NaN
  }
}

export function drawGrid(ctx: CanvasRenderingContext2D, W: number, H: number, gridOn: boolean): void {
  ctx.clearRect(0, 0, W, H)
  if (!gridOn) return
  ctx.strokeStyle = '#e4e9f0'
  ctx.lineWidth = 1
  for (let i = -10; i <= 10; i += 2) {
    let a = gwXY(i, -10)
    let b = gwXY(i, 10)
    ctx.beginPath()
    ctx.moveTo(a[0], a[1])
    ctx.lineTo(b[0], b[1])
    ctx.stroke()
    a = gwXY(-10, i)
    b = gwXY(10, i)
    ctx.beginPath()
    ctx.moveTo(a[0], a[1])
    ctx.lineTo(b[0], b[1])
    ctx.stroke()
  }
  ctx.strokeStyle = '#8a94a6'
  ctx.lineWidth = 1.5
  let a = gwXY(-10, 0)
  let b = gwXY(10, 0)
  ctx.beginPath()
  ctx.moveTo(a[0], a[1])
  ctx.lineTo(b[0], b[1])
  ctx.stroke()
  a = gwXY(0, -10)
  b = gwXY(0, 10)
  ctx.beginPath()
  ctx.moveTo(a[0], a[1])
  ctx.lineTo(b[0], b[1])
  ctx.stroke()
}

export function drawCurve(
  ctx: CanvasRenderingContext2D,
  fn: (x: number) => number,
  color: string,
  dash = false,
): void {
  ctx.strokeStyle = color
  ctx.lineWidth = 2.2
  if (dash) ctx.setLineDash([7, 5])
  ctx.beginPath()
  let started = false
  for (let px = 0; px <= GW_W; px += 2) {
    const x = -10 + (20 * px) / GW_W
    const y = fn(x)
    if (!isFinite(y) || Math.abs(y) > 14) {
      started = false
      continue
    }
    const [cx, cy] = gwXY(x, y)
    if (!started) {
      ctx.moveTo(cx, cy)
      started = true
    } else {
      ctx.lineTo(cx, cy)
    }
  }
  ctx.stroke()
  ctx.setLineDash([])
}

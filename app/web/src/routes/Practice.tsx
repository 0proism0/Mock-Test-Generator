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

function mkFrac(n: number, d: number): DrQ {
  const g = gcd(Math.abs(n), d)
  const sn = n / g
  const sd = d / g
  return { q: '', v: sn / sd, disp: sd === 1 ? String(sn) : `${sn}/${sd}`, frac: true }
}

function genMul2(lv: Level): DrQ {
  let a: number, b: number
  if (lv === 'easy') { a = rnd(11, 19); b = rnd(3, 9) }
  else if (lv === 'medium') { a = rnd(21, 99); b = rnd(3, 9) }
  else { a = rnd(12, 49); b = rnd(12, 19) }
  return { q: `${a} × ${b} = ?`, v: a * b }
}

function genPemdas(lv: Level): DrQ {
  if (lv === 'easy') {
    const a = rnd(2, 30), b = rnd(2, 9), c = rnd(2, 9)
    return { q: `${a} + ${b} × ${c} = ?`, v: a + b * c }
  }
  if (lv === 'medium') {
    const a = rnd(2, 20), b = rnd(2, 20), c = rnd(2, 9)
    return { q: `(${a} + ${b}) × ${c} = ?`, v: (a + b) * c }
  }
  const a = rnd(2, 9), b = rnd(2, 9), c = rnd(2, 9), d = rnd(2, 9), e = rnd(2, 9)
  return { q: `${a} × ${b} + ${c} × ${d} − ${e} = ?`, v: a * b + c * d - e }
}

function genNeg(lv: Level): DrQ {
  if (lv === 'easy') {
    const a = rnd(2, 20), b = rnd(2, 30)
    return { q: `−${a} + ${b} = ?`, v: b - a }
  }
  if (lv === 'medium') {
    const a = rnd(2, 20), b = rnd(2, 20)
    return Math.random() < 0.5
      ? { q: `−${a} − ${b} = ?`, v: -a - b }
      : { q: `−${a} × ${b} = ?`, v: -a * b }
  }
  const a = rnd(2, 12), b = rnd(2, 12), c = rnd(2, 20)
  return { q: `−${a} × (−${b}) − ${c} = ?`, v: a * b - c }
}

function genAbs(lv: Level): DrQ {
  if (lv === 'easy') {
    const a = rnd(2, 30)
    return { q: `|−${a}| = ?`, v: a }
  }
  if (lv === 'medium') {
    const a = rnd(2, 15), b = rnd(16, 40)
    return { q: `|${a} − ${b}| = ?`, v: b - a }
  }
  const a = rnd(2, 20), b = rnd(2, 20), c = rnd(2, 20), d = rnd(2, 20)
  const v1 = Math.abs(a - b), v2 = Math.abs(c - d)
  return { q: `|${a} − ${b}| + |${c} − ${d}| = ?`, v: v1 + v2 }
}

function genRound(lv: Level): DrQ {
  if (lv === 'easy') {
    const n = rnd(11, 99) * 10 + rnd(1, 9)
    return { q: `Round ${n} to the nearest 10`, v: Math.round(n / 10) * 10 }
  }
  if (lv === 'medium') {
    const n = rnd(1001, 9999)
    return { q: `Round ${n} to the nearest 100`, v: Math.round(n / 100) * 100 }
  }
  const n = rnd(100001, 999999)
  return { q: `Round ${n} to the nearest 1000`, v: Math.round(n / 1000) * 1000 }
}

function genBase(lv: Level): DrQ {
  if (lv === 'easy') {
    const n = rnd(5, 63)
    return { q: `${n.toString(2)} (base 2) = ? (base 10)`, v: n }
  }
  if (lv === 'medium') {
    const n = rnd(33, 200)
    return { q: `${n} in binary = ? (type the digits)`, v: parseInt(n.toString(2), 10) }
  }
  const n = rnd(50, 255)
  return Math.random() < 0.5
    ? { q: `0x${n.toString(16)} (hex) = ? (base 10)`, v: n }
    : { q: `${n} in binary = ? (type the digits)`, v: parseInt(n.toString(2), 10) }
}

function genFdiv(lv: Level): DrQ {
  let a: number, b: number, c: number, d: number
  if (lv === 'easy') { a = rnd(1, 5); b = rnd(2, 6); c = rnd(1, 5); d = rnd(2, 6) }
  else if (lv === 'medium') { a = rnd(2, 9); b = rnd(3, 9); c = rnd(2, 9); d = rnd(3, 9) }
  else { a = rnd(3, 12); b = rnd(4, 12); c = rnd(3, 12); d = rnd(4, 12) }
  const r = mkFrac(a * d, b * c)
  return { ...r, q: `$\\frac{${a}}{${b}} \\div \\frac{${c}}{${d}} = ?$` }
}

function genMixed(lv: Level): DrQ {
  const w = lv === 'easy' ? rnd(1, 5) : lv === 'medium' ? rnd(2, 9) : rnd(3, 15)
  const [lo, hi] = lv === 'easy' ? [2, 6] : lv === 'medium' ? [3, 9] : [4, 12]
  let n = rnd(1, hi - 1), d = rnd(lo, hi)
  if (n === d) n -= 1
  return { q: `Write $${w}\\frac{${n}}{${d}}$ as an improper fraction $\\frac{a}{b}$. What is $a$?`, v: w * d + n }
}

function genDec(lv: Level): DrQ {
  if (lv === 'easy') {
    const a = rnd(11, 99) / 10, b = rnd(11, 99) / 10
    return { q: `${a} + ${b} = ?`, v: Math.round((a + b) * 100) / 100 }
  }
  if (lv === 'medium') {
    const a = rnd(11, 99) / 10, b = rnd(3, 9) / 10
    return { q: `${a} × ${b} = ?`, v: Math.round(a * b * 1000) / 1000 }
  }
  const b = rnd(2, 9) / 10
  const q2 = rnd(3, 12)
  const a = Math.round(b * q2 * 100) / 100
  return { q: `${a} ÷ ${b} = ?`, v: q2 }
}

function genFdp(lv: Level): DrQ {
  if (Math.random() < 0.5) {
    const fracs: [number, number][] = lv === 'easy' ? [[1, 2], [1, 4], [3, 4], [1, 5]]
      : lv === 'medium' ? [[1, 8], [3, 8], [5, 8], [7, 8], [2, 5]]
      : [[1, 16], [3, 16], [5, 16], [7, 25], [11, 25]]
    const [n, d] = fracs[rnd(0, fracs.length - 1)]
    return { q: `$\\frac{${n}}{${d}}$ as a decimal = ?`, v: n / d }
  }
  const denoms = lv === 'hard' ? [8, 16, 20, 25, 40, 50] : null
  const r = lv === 'easy' ? mkFrac(rnd(1, 4) * 25, 100)
    : lv === 'medium' ? mkFrac(rnd(1, 8) * 125, 1000)
    : (() => { const d = denoms![rnd(0, denoms!.length - 1)]; return mkFrac(rnd(1, d - 1), d) })()
  return { ...r, q: `${r.v} as a simplified fraction = ? (a/b)` }
}

function genPctChg(lv: Level): DrQ {
  const p = lv === 'easy' ? [10, 25, 50][rnd(0, 2)] : lv === 'medium' ? rnd(2, 19) * 5 : rnd(1, 99)
  const a = (lv === 'hard' ? rnd(1, 12) : rnd(2, 20)) * (100 / gcd(p, 100))
  const up = Math.random() < 0.5
  const b = Math.round(a * (up ? 1 + p / 100 : 1 - p / 100))
  return { q: `A price changes from ${a} to ${b}. Percent ${up ? 'increase' : 'decrease'} = ?%`, v: p }
}

function genDiscount(lv: Level): DrQ {
  const p = lv === 'easy' ? [10, 25, 50][rnd(0, 2)] : lv === 'medium' ? rnd(2, 19) * 5 : rnd(1, 40)
  const price = rnd(2, 20) * (100 / gcd(p, 100))
  return { q: `A ${price} item is discounted by ${p}%. New price = ?`, v: (price * (100 - p)) / 100 }
}

function genInterest(lv: Level): DrQ {
  const r = lv === 'easy' ? [5, 10][rnd(0, 1)] : lv === 'medium' ? [4, 5, 8, 10][rnd(0, 3)] : rnd(2, 12)
  const t = lv === 'easy' ? rnd(1, 2) : lv === 'medium' ? rnd(1, 4) : rnd(2, 8)
  const P = rnd(50, 500) * (100 / gcd(r * t, 100))
  return { q: `$${P} is invested at ${r}% simple interest for ${t} year${t > 1 ? 's' : ''}. Total interest = ?`, v: (P * r * t) / 100 }
}

function genRatio(lv: Level): DrQ {
  if (lv === 'easy') {
    const a = rnd(1, 5), b = rnd(1, 5), c = a * rnd(2, 6)
    return { q: `If $a:${b} = ${c}:x$, what is $x$?`, v: (b * c) / a }
  }
  if (lv === 'medium') {
    const a = rnd(2, 7), b = rnd(2, 7), total = (a + b) * rnd(2, 6)
    return { q: `Divide ${total} in the ratio $${a}:${b}$. The larger share = ?`, v: (Math.max(a, b) * total) / (a + b) }
  }
  const a = rnd(2, 5), b = rnd(2, 5), c = rnd(2, 5), total = (a + b + c) * rnd(2, 5)
  return { q: `Split ${total} in the ratio $${a}:${b}:${c}$. The smallest share = ?`, v: (Math.min(a, b, c) * total) / (a + b + c) }
}

function genCbrt(lv: Level): DrQ {
  const a = lv === 'easy' ? rnd(1, 5) : lv === 'medium' ? rnd(5, 12) : rnd(13, 25)
  return { q: `∛${a ** 3} = ?`, v: a }
}

function genNexp(lv: Level): DrQ {
  if (lv === 'easy') {
    const n = rnd(2, 5)
    const r = mkFrac(1, 2 ** n)
    return { ...r, q: `$2^{-${n}}$ = ? (a/b)` }
  }
  if (lv === 'medium') {
    const a = rnd(2, 5), n = rnd(2, 4)
    const r = mkFrac(1, a ** n)
    return { ...r, q: `$${a}^{-${n}}$ = ? (a/b)` }
  }
  const a = rnd(2, 4), n = rnd(2, 3), m = rnd(1, 3)
  const r = mkFrac(a ** m, a ** (m + n))
  return { ...r, q: `$\\frac{${a ** m}}{${a ** (m + n)}}$ as $${a}^{?}$: what is the exponent?`, v: -n }
}

function genSci(lv: Level): DrQ {
  if (lv === 'easy') {
    const a = rnd(11, 99) / 10, n = rnd(1, 4)
    return { q: `$${a} \\times 10^{${n}}$ = ?`, v: a * 10 ** n }
  }
  if (lv === 'medium') {
    const a = rnd(11, 99) / 10
    const n = rnd(1, 5)
    const v = a * 10 ** n
    return { q: `${v} = a × 10^n in scientific notation. What is $a$?`, v: a }
  }
  const a = rnd(11, 99) / 10, b = rnd(11, 99) / 10, m = rnd(1, 4), n = rnd(1, 4)
  const prod = a * b
  return { q: `$( ${a} \\times 10^{${m}} )( ${b} \\times 10^{${n}} ) = c \\times 10^{?}$, with $1 \\le c < 10$. What is $c$?`, v: Math.round(prod * 100) / 100 }
}

function genLog(lv: Level): DrQ {
  if (lv === 'easy') {
    const n = rnd(1, 4)
    return { q: `$\\log_{10} ${10 ** n}$ = ?`, v: n }
  }
  if (lv === 'medium') {
    const n = rnd(2, 7)
    return { q: `$\\log_2 ${2 ** n}$ = ?`, v: n }
  }
  const b = [3, 5][rnd(0, 1)], n = rnd(2, 4)
  return { q: `$\\log_${b} ${b ** n}$ = ?`, v: n }
}

function genParens(lv: Level): DrQ {
  if (lv === 'easy') {
    const a = 2, x = rnd(1, 10), b = rnd(1, 8)
    return { q: `Solve: $${a}(x + ${b}) = ${a * (x + b)}$`, v: x }
  }
  if (lv === 'medium') {
    const a = rnd(2, 5), x = rnd(1, 10), b = rnd(1, 8)
    return { q: `Solve: $${a}(x + ${b}) = ${a * (x + b)}$`, v: x }
  }
  const a = rnd(2, 5), x = rnd(1, 9), b = rnd(1, 8), c = rnd(1, 20)
  return { q: `Solve: $${a}(x + ${b}) + ${c} = ${a * (x + b) + c}$`, v: x }
}

function genSlope(lv: Level): DrQ {
  const [lo, hi] = lv === 'easy' ? [1, 9] : lv === 'medium' ? [-9, 9] : [-15, 15]
  const x1 = rnd(-5, 5), y1 = rnd(-9, 9)
  const m = rnd(lo, hi)
  const dx = lv === 'easy' ? rnd(1, 4) : rnd(1, 6)
  const x2 = x1 + dx, y2 = y1 + m * dx
  return { q: `Slope through $( ${x1}, ${y1} )$ and $( ${x2}, ${y2} )$ = ?`, v: m }
}

function genLine(lv: Level): DrQ {
  const m = lv === 'easy' ? rnd(1, 5) : lv === 'medium' ? rnd(-6, 6) : rnd(-9, 9)
  const b = lv === 'hard' ? rnd(-12, 12) : rnd(-8, 8)
  const x = rnd(1, 5), y = m * x + b
  return { q: `A line with slope $${m}$ passes through $( ${x}, ${y} )$. Its y-intercept $b$ = ?`, v: b }
}

function genDistmid(lv: Level): DrQ {
  if (lv === 'easy') {
    const x1 = rnd(0, 8), x2 = rnd(0, 8), y1 = rnd(0, 8), y2 = rnd(0, 8)
    return { q: `x-coordinate of the midpoint of $( ${x1}, ${y1} )$ and $( ${x2}, ${y2} )$ = ?`, v: (x1 + x2) / 2 }
  }
  const triples: [number, number, number][] = [[3, 4, 5], [6, 8, 10], [5, 12, 13], [9, 12, 15], [8, 15, 17], [7, 24, 25], [12, 16, 20], [20, 21, 29], [10, 24, 26], [18, 24, 30]]
  const [a, b, c] = triples[rnd(0, lv === 'medium' ? 4 : triples.length - 1)]
  const x1 = rnd(0, 6), y1 = rnd(0, 6)
  return { q: `Distance from $( ${x1}, ${y1} )$ to $( ${x1 + a}, ${y1 + b} )$ = ?`, v: c }
}

function genSystem(lv: Level): DrQ {
  if (lv === 'easy') {
    const x = rnd(1, 12), y = rnd(1, 12)
    return { q: `If $x + y = ${x + y}$ and $x − y = ${x - y}$, then $x$ = ?`, v: x }
  }
  if (lv === 'medium') {
    const x = rnd(1, 9), y = rnd(1, 9)
    return { q: `If $x + 2y = ${x + 2 * y}$ and $x − 2y = ${x - 2 * y}$, then $x$ = ?`, v: x }
  }
  const a = rnd(2, 4), b = rnd(2, 4), x = rnd(1, 6), y = rnd(1, 6)
  return { q: `If $${a}x + ${b}y = ${a * x + b * y}$ and $${a}x − ${b}y = ${a * x - b * y}$, then $x$ = ?`, v: x }
}

function genQuad(lv: Level): DrQ {
  const [lo, hi] = lv === 'easy' ? [1, 8] : lv === 'medium' ? [-9, 9] : [-15, 15]
  const r1 = rnd(lo, hi), r2 = rnd(lo, hi)
  const bSum = -(r1 + r2)
  const bTxt = bSum === 0 ? '' : bSum > 0 ? ` + ${bSum}x` : ` − ${Math.abs(bSum)}x`
  const c = r1 * r2
  const cTxt = c === 0 ? '' : c > 0 ? ` + ${c}` : ` − ${Math.abs(c)}`
  return { q: `For $x^2${bTxt}${cTxt} = 0$, the sum of the roots = ?`, v: -bSum }
}

function genDisc(lv: Level): DrQ {
  const [lo, hi] = lv === 'easy' ? [1, 6] : lv === 'medium' ? [-8, 8] : [-12, 12]
  const b = rnd(lo, hi), c = rnd(-9, 9)
  const bTxt = b === 0 ? '' : b > 0 ? ` + ${b}x` : ` − ${Math.abs(b)}x`
  const cTxt = c === 0 ? '' : c > 0 ? ` + ${c}` : ` − ${Math.abs(c)}`
  return { q: `Discriminant of $x^2${bTxt}${cTxt} = 0$ ($b^2 − 4ac$) = ?`, v: b * b - 4 * c }
}

function nz(lo: number, hi: number): number {
  let v = 0
  while (v === 0) v = rnd(lo, hi)
  return v
}

function genFactor(lv: Level): DrQ {
  const [lo, hi] = lv === 'easy' ? [1, 6] : lv === 'medium' ? [-7, 7] : [-9, 9]
  const a = nz(lo, hi), b = nz(lo, hi)
  const aTxt = a >= 0 ? `+ ${a}` : `− ${Math.abs(a)}`
  const bTxt = b >= 0 ? `+ ${b}` : `− ${Math.abs(b)}`
  if (lv === 'hard' && Math.random() < 0.5) {
    const c = rnd(1, 5)
    return { q: `Constant term of $(x ${aTxt})(x ${bTxt})(x + ${c})$ = ?`, v: a * b * c }
  }
  return { q: `Constant term of $(x ${aTxt})(x ${bTxt})$ = ?`, v: a * b }
}

function genFeval(lv: Level): DrQ {
  if (lv === 'easy') {
    const a = rnd(2, 6), b = rnd(-9, 9), k = rnd(-5, 5)
    return { q: `If $f(x) = ${a}x ${b >= 0 ? '+ ' + b : '− ' + Math.abs(b)}$, then $f(${k})$ = ?`, v: a * k + b }
  }
  if (lv === 'medium') {
    const a = rnd(1, 3), b = rnd(-6, 6), c = rnd(-6, 6), k = rnd(-4, 4)
    const bTxt = b === 0 ? '' : b > 0 ? ` + ${b}x` : ` − ${Math.abs(b)}x`
    const cTxt = c === 0 ? '' : c > 0 ? ` + ${c}` : ` − ${Math.abs(c)}`
    return { q: `If $f(x) = ${a}x^2${bTxt}${cTxt}$, then $f(${k})$ = ?`, v: a * k * k + b * k + c }
  }
  const a = rnd(-4, 4) || 2, b = rnd(-6, 6), k = rnd(-5, 5)
  return { q: `If $f(x) = ${a}x^2 ${b >= 0 ? '+ ' + b : '− ' + Math.abs(b)}$, then $f(${k})$ = ?`, v: a * k * k + b }
}

function genPfactor(lv: Level): DrQ {
  const count = lv === 'easy' ? 2 : lv === 'medium' ? 3 : 4
  let n = 1
  const primes = [2, 3, 5, 7, 11, 13]
  for (let i = 0; i < count; i++) n *= primes[rnd(0, lv === 'easy' ? 2 : lv === 'medium' ? 3 : 5)]
  return { q: `How many prime factors does ${n} have (counted with multiplicity)?`, v: count }
}

function genMod(lv: Level): DrQ {
  const d = lv === 'easy' ? [2, 5, 10][rnd(0, 2)] : lv === 'medium' ? [3, 4, 6, 9][rnd(0, 3)] : [7, 8, 11, 13][rnd(0, 3)]
  const n = rnd(d * 2, d * 25 + 9)
  return { q: `Remainder when ${n} is divided by ${d} = ?`, v: n % d }
}

function genLastdig(lv: Level): DrQ {
  const a = lv === 'easy' ? [2, 5, 6][rnd(0, 2)] : lv === 'medium' ? [3, 4, 7, 8, 9][rnd(0, 4)] : rnd(2, 99)
  const n = lv === 'easy' ? rnd(3, 15) : lv === 'medium' ? rnd(5, 30) : rnd(11, 60)
  let last = 1
  for (let i = 0; i < n; i++) last = (last * a) % 10
  return { q: `Last digit of $${a}^{${n}}$ = ?`, v: last }
}

function genFact(lv: Level): DrQ {
  if (lv !== 'hard') {
    const n = lv === 'easy' ? rnd(3, 5) : rnd(6, 8)
    let f = 1
    for (let i = 2; i <= n; i++) f *= i
    return { q: `$${n}!$ = ?`, v: f }
  }
  const n = rnd(20, 150)
  let z = 0
  for (let p = 5; p <= n; p *= 5) z += Math.floor(n / p)
  return { q: `Trailing zeros of $${n}!$ = ?`, v: z }
}

function nPr(n: number, r: number): number {
  let v = 1
  for (let i = 0; i < r; i++) v *= n - i
  return v
}
function nCr(n: number, r: number): number {
  r = Math.min(r, n - r)
  let v = 1
  for (let i = 0; i < r; i++) v = (v * (n - i)) / (i + 1)
  return Math.round(v)
}

function genPerm(lv: Level): DrQ {
  const [n, r] = lv === 'easy' ? [rnd(4, 6), 2] : lv === 'medium' ? [rnd(5, 8), 3] : [rnd(8, 12), 3]
  return { q: `$P(${n}, ${r}) = \\frac{${n}!}{(${n} - ${r})!}$ = ?`, v: nPr(n, r) }
}

function genComb(lv: Level): DrQ {
  const [n, r] = lv === 'easy' ? [[5, 2], [6, 2], [6, 3], [7, 2]][rnd(0, 3)]
    : lv === 'medium' ? [[8, 3], [9, 2], [10, 2], [7, 4]][rnd(0, 3)]
    : [[10, 4], [12, 3], [9, 5], [11, 4]][rnd(0, 3)]
  return { q: `$\\binom{${n}}{${r}}$ = ?`, v: nCr(n, r) }
}

function genProb(lv: Level): DrQ {
  if (lv === 'easy') {
    const kind = rnd(0, 2)
    if (kind === 0) return { ...mkFrac(1, 2), q: 'A fair coin is flipped. P(heads) = ? (a/b)' }
    if (kind === 1) return { ...mkFrac(1, 2), q: 'A die is rolled. P(even) = ? (a/b)' }
    return { ...mkFrac(1, 3), q: 'A die is rolled. P(multiple of 3) = ? (a/b)' }
  }
  if (lv === 'medium') {
    const r = rnd(2, 6), b = rnd(2, 6)
    return { ...mkFrac(r, r + b), q: `A bag has ${r} red and ${b} blue marbles. P(red) = ? (a/b)` }
  }
  const r = rnd(3, 7), b = rnd(3, 7)
  return { ...mkFrac(b * (b - 1), (r + b) * (r + b - 1)), q: `A bag has ${r} red and ${b} blue marbles. Draw one, keep it, draw again. P(both blue) = ? (a/b)` }
}

function genDice(lv: Level): DrQ {
  const sums = Array.from({ length: 11 }, (_, i) => i + 2).map((s) => {
    let c = 0
    for (let a = 1; a <= 6; a++) for (let b = 1; b <= 6; b++) if (a + b === s) c++
    return [s, c] as [number, number]
  })
  if (lv === 'easy') {
    const s = [7, 8][rnd(0, 1)]
    const c = sums.find(([x]) => x === s)![1]
    return { ...mkFrac(c, 36), q: `Two dice are rolled. P(sum = ${s}) = ? (a/b)` }
  }
  if (lv === 'medium') {
    const s = rnd(4, 10)
    const c = sums.find(([x]) => x === s)![1]
    return { ...mkFrac(c, 36), q: `Two dice are rolled. P(sum = ${s}) = ? (a/b)` }
  }
  const c = sums.filter(([s]) => s > 9).reduce((a, [, n]) => a + n, 0)
  return { ...mkFrac(c, 36), q: 'Two dice are rolled. P(sum > 9) = ? (a/b)' }
}

function genPyth(lv: Level): DrQ {
  const triples: [number, number, number][] = [[3, 4, 5], [6, 8, 10], [5, 12, 13], [9, 12, 15], [8, 15, 17], [7, 24, 25], [12, 16, 20], [20, 21, 29], [10, 24, 26], [15, 20, 25], [18, 24, 30]]
  const [a, b, c] = triples[rnd(0, lv === 'easy' ? 3 : lv === 'medium' ? 7 : triples.length - 1)]
  if (Math.random() < 0.5) return { q: `Legs ${a} and ${b}. Hypotenuse = ?`, v: c }
  return { q: `A right triangle has hypotenuse ${c} and one leg ${a}. Other leg = ?`, v: b }
}

function genTri(lv: Level): DrQ {
  if (lv === 'easy') {
    const a = rnd(30, 80), b = rnd(30, 80)
    return { q: `Two angles of a triangle are ${a}° and ${b}°. The third = ?°`, v: 180 - a - b }
  }
  if (lv === 'medium') {
    return { q: `A triangle's angles are $x$, $2x$, $3x$. The smallest = ?°`, v: 30 }
  }
  const ext = rnd(80, 140), remote1 = rnd(20, 60)
  return { q: `An exterior angle of a triangle is ${ext}°; one remote interior angle is ${remote1}°. The other = ?°`, v: ext - remote1 }
}

function genCircle(lv: Level): DrQ {
  if (lv === 'easy') {
    const r = rnd(2, 12)
    return { q: `A circle has radius ${r}. Its area is $\\pi k$; $k$ = ?`, v: r * r }
  }
  if (lv === 'medium') {
    const r = rnd(2, 12)
    return { q: `A circle has radius ${r}. Its circumference is $\\pi k$; $k$ = ?`, v: 2 * r }
  }
  const k = rnd(2, 12)
  return { q: `A circle's area is $\\pi \\cdot ${k * k}$. Its radius = ?`, v: k }
}

function genVol(lv: Level): DrQ {
  if (lv === 'easy') {
    const a = rnd(2, 9), b = rnd(2, 9), c = rnd(2, 9)
    return { q: `Volume of a ${a} × ${b} × ${c} box = ?`, v: a * b * c }
  }
  if (lv === 'medium') {
    const r = rnd(2, 9), h = rnd(2, 9)
    return { q: `A cylinder has r = ${r}, h = ${h}. Its volume is $\\pi k$; $k$ = ?`, v: r * r * h }
  }
  const r = rnd(2, 9)
  return { q: `A sphere has radius ${r}. Its volume is $\\pi k/3$; $k$ = ?`, v: 4 * r ** 3 }
}

function genDrt(lv: Level): DrQ {
  if (lv === 'easy') {
    const r = rnd(2, 8) * 5, t = rnd(2, 6)
    return { q: `A car drives ${r} km/h for ${t} hours. Distance = ? km`, v: r * t }
  }
  if (lv === 'medium') {
    const r = rnd(3, 9) * 10, d = r * rnd(2, 5)
    return { q: `A train covers ${d} km at ${r} km/h. Time = ? hours`, v: d / r }
  }
  const r1 = rnd(30, 60), r2 = rnd(30, 60), t1 = rnd(1, 3), t2 = rnd(1, 3)
  return { q: `A trip: ${r1} km/h for ${t1} h, then ${r2} km/h for ${t2} h. Total distance = ? km`, v: r1 * t1 + r2 * t2 }
}

function genAvg(lv: Level): DrQ {
  const n = lv === 'easy' ? 3 : lv === 'medium' ? 4 : 5
  const avg = rnd(8, 25)
  const nums = Array.from({ length: n - 1 }, () => rnd(5, 30))
  const missing = avg * n - nums.reduce((a, b) => a + b, 0)
  if (missing < 5 || missing > 30) return genAvg(lv)
  return { q: `The average of ${nums.join(', ')}, and one more number is ${avg}. The missing number = ?`, v: missing }
}

function genAseq(lv: Level): DrQ {
  if (lv === 'easy') {
    const a1 = rnd(1, 10), d = rnd(2, 9), n = rnd(5, 15)
    return { q: `An arithmetic sequence has first term ${a1} and common difference ${d}. Term #${n} = ?`, v: a1 + (n - 1) * d }
  }
  if (lv === 'medium') {
    const a1 = rnd(1, 12), d = rnd(2, 9), n = rnd(5, 12)
    return { q: `Term #1 of an arithmetic sequence is ${a1}; term #${n} is ${a1 + (n - 1) * d}. Common difference = ?`, v: d }
  }
  const a1 = rnd(1, 9), d = rnd(2, 9), n = rnd(6, 20)
  const target = a1 + (n - 1) * d
  return { q: `An arithmetic sequence starts at ${a1} with difference ${d}. Which term number equals ${target}?`, v: n }
}

const DRILLS: Record<string, { name: string; desc: string; gen: (lv: Level) => DrQ }> = {
  addsub: { name: 'drAddSub', desc: 'drAddSubDesc', gen: genAddSub },
  mul2: { name: 'drMul2', desc: 'drMul2Desc', gen: genMul2 },
  pemdas: { name: 'drPemdas', desc: 'drPemdasDesc', gen: genPemdas },
  neg: { name: 'drNeg', desc: 'drNegDesc', gen: genNeg },
  absv: { name: 'drAbs', desc: 'drAbsDesc', gen: genAbs },
  round: { name: 'drRound', desc: 'drRoundDesc', gen: genRound },
  base: { name: 'drBase', desc: 'drBaseDesc', gen: genBase },
  mult: { name: 'drMult', desc: 'drMultDesc', gen: genMult },
  div: { name: 'drDiv', desc: 'drDivDesc', gen: genDiv },
  mod: { name: 'drMod', desc: 'drModDesc', gen: genMod },
  lastdig: { name: 'drLastDig', desc: 'drLastDigDesc', gen: genLastdig },
  fact: { name: 'drFact', desc: 'drFactDesc', gen: genFact },
  frac: { name: 'drFrac', desc: 'drFracDesc', gen: genFrac },
  fdiv: { name: 'drFdiv', desc: 'drFdivDesc', gen: genFdiv },
  mixed: { name: 'drMixed', desc: 'drMixedDesc', gen: genMixed },
  dec: { name: 'drDec', desc: 'drDecDesc', gen: genDec },
  fdp: { name: 'drFdp', desc: 'drFdpDesc', gen: genFdp },
  pct: { name: 'drPct', desc: 'drPctDesc', gen: genPct },
  pctchg: { name: 'drPctChg', desc: 'drPctChgDesc', gen: genPctChg },
  discount: { name: 'drDiscount', desc: 'drDiscountDesc', gen: genDiscount },
  interest: { name: 'drInterest', desc: 'drInterestDesc', gen: genInterest },
  ratio: { name: 'drRatio', desc: 'drRatioDesc', gen: genRatio },
  pow: { name: 'drPow', desc: 'drPowDesc', gen: genPow },
  cbrt: { name: 'drCbrt', desc: 'drCbrtDesc', gen: genCbrt },
  nexp: { name: 'drNexp', desc: 'drNexpDesc', gen: genNexp },
  sci: { name: 'drSci', desc: 'drSciDesc', gen: genSci },
  log: { name: 'drLog', desc: 'drLogDesc', gen: genLog },
  eq: { name: 'drEq', desc: 'drEqDesc', gen: genEq },
  parens: { name: 'drParens', desc: 'drParensDesc', gen: genParens },
  slope: { name: 'drSlope', desc: 'drSlopeDesc', gen: genSlope },
  line: { name: 'drLine', desc: 'drLineDesc', gen: genLine },
  distmid: { name: 'drDistmid', desc: 'drDistmidDesc', gen: genDistmid },
  system: { name: 'drSystem', desc: 'drSystemDesc', gen: genSystem },
  quad: { name: 'drQuad', desc: 'drQuadDesc', gen: genQuad },
  disc: { name: 'drDisc', desc: 'drDiscDesc', gen: genDisc },
  factor: { name: 'drFactor', desc: 'drFactorDesc', gen: genFactor },
  feval: { name: 'drFeval', desc: 'drFevalDesc', gen: genFeval },
  gcdlcm: { name: 'drGcdLcm', desc: 'drGcdLcmDesc', gen: genGcdLcm },
  pfactor: { name: 'drPfactor', desc: 'drPfactorDesc', gen: genPfactor },
  perm: { name: 'drPerm', desc: 'drPermDesc', gen: genPerm },
  comb: { name: 'drComb', desc: 'drCombDesc', gen: genComb },
  prob: { name: 'drProb', desc: 'drProbDesc', gen: genProb },
  dice: { name: 'drDice', desc: 'drDiceDesc', gen: genDice },
  pyth: { name: 'drPyth', desc: 'drPythDesc', gen: genPyth },
  tri: { name: 'drTri', desc: 'drTriDesc', gen: genTri },
  circle: { name: 'drCircle', desc: 'drCircleDesc', gen: genCircle },
  vol: { name: 'drVol', desc: 'drVolDesc', gen: genVol },
  drt: { name: 'drDrt', desc: 'drDrtDesc', gen: genDrt },
  avg: { name: 'drAvg', desc: 'drAvgDesc', gen: genAvg },
  aseq: { name: 'drAseq', desc: 'drAseqDesc', gen: genAseq },
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
            <div key={key} data-drill={key} className="card compact">
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

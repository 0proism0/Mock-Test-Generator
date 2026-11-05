import { api, type ResultDetail, type TestResult } from './api'

// ---------- shared types ----------

export interface AnQuestion {
  n: number
  source?: string
  question: string
  choices?: Record<string, string>
  answer: string
  solution?: string
  type?: string
  points?: number
  /** Bank-embedded classifier output (see classifier/ + taxonomy/amc-v1.json). */
  classification?: {
    primary?: string
    tags?: { id: string; weight?: number }[]
    note?: string
  }
  difficulty?: { level?: number; band?: string }
}

export interface AnTest {
  id: string
  title: string
  competition: string
  instructions?: string
  time_limit_min?: number
  total_points?: number
  questions: AnQuestion[]
}

export interface QClass {
  kp?: string
  diff?: number
  note?: string
}

export type ClassMap = Record<string, QClass>

/** One wrong/blank question occurrence, joined with its test + classification. */
export interface MissedItem {
  test_id: string
  test_title: string
  submitted_at: string
  n: number
  given: string
  answer: string
  kp: string
  note: string
  diff?: number
  question: string
}

/** Resolve a question's knowledge point: teacher classification wins, then the
 * bank-embedded classifier tag (labelled via the taxonomy). */
export type KpResolver = (testId: string, n: number) => { kp: string; note: string; diff?: number }

export function makeKpResolver(
  tests: Record<string, AnTest>,
  classes: Record<string, ClassMap>,
  tax: { nodes: Record<string, { en: string; zh: string }> } | null,
  lang: string,
): KpResolver {
  return (testId, n) => {
    const cls = classes[testId]?.[String(n)]
    const q = tests[testId]?.questions.find((x) => x.n === n)
    let kp = cls?.kp ?? ''
    let note = cls?.note ?? ''
    let diff = cls?.diff
    const primary = q?.classification?.primary
    if (!kp && primary && tax?.nodes[primary]) {
      const node = tax.nodes[primary]
      kp = (lang === 'zh' ? node.zh : node.en) || node.en
      if (!note && q?.classification?.note) note = q.classification.note
    }
    if (diff == null && q?.difficulty?.level) diff = q.difficulty.level
    return { kp: kp || '—', note, diff }
  }
}

// ---------- data loading (with per-session cache) ----------

const testCache = new Map<string, Promise<AnTest>>()
const clsCache = new Map<string, Promise<ClassMap>>()

export function loadTest(id: string): Promise<AnTest> {
  let p = testCache.get(id)
  if (!p) {
    p = api.test(id) as Promise<AnTest>
    testCache.set(id, p)
    p.catch(() => testCache.delete(id))
  }
  return p
}

export function loadClassMap(id: string): Promise<ClassMap> {
  let p = clsCache.get(id)
  if (!p) {
    p = api
      .classify(id)
      .then((d) => d.items as ClassMap)
      .catch(() => ({}))
    clsCache.set(id, p)
  }
  return p
}

/** Drop cached classifications (call after a teacher saves new ones). */
export function bustClassCache(id?: string) {
  if (id) clsCache.delete(id)
  else clsCache.clear()
}

export async function loadAnalysisData(results: TestResult[]) {
  const ids = [...new Set(results.map((r) => r.test_id))]
  const tests: Record<string, AnTest> = {}
  const classes: Record<string, ClassMap> = {}
  await Promise.all(
    ids.map(async (id) => {
      const [t, c] = await Promise.all([loadTest(id).catch(() => null), loadClassMap(id)])
      if (t) tests[id] = t
      classes[id] = c
    }),
  )
  return { tests, classes }
}

// ---------- aggregation ----------

/** Split positions 1..n into 4 contiguous bands (1-indexed, inclusive). */
export function bands(n: number): [number, number][] {
  const size = Math.ceil(n / 4)
  const out: [number, number][] = []
  for (let lo = 1; lo <= n; lo += size) out.push([lo, Math.min(n, lo + size - 1)])
  return out
}

export interface AttemptStats {
  result: TestResult
  correct: number
  wrong: number
  blank: number
  answered: number
  accuracy: number // % of answered that were correct
  bandScores: { lo: number; hi: number; ok: number; total: number }[]
  missed: { detail: ResultDetail; q?: AnQuestion; cls?: QClass }[]
}

export function attemptStats(result: TestResult, test: AnTest | undefined, cls: ClassMap | undefined): AttemptStats {
  const details = result.details ?? []
  const byN = new Map((test?.questions ?? []).map((q) => [q.n, q]))
  let correct = 0
  let wrong = 0
  let blank = 0
  const missed: AttemptStats['missed'] = []
  for (const d of details) {
    if (d.ok) {
      correct++
      continue
    }
    if (!d.given) blank++
    else wrong++
    missed.push({ detail: d, q: byN.get(d.n), cls: cls?.[String(d.n)] })
  }
  const answered = correct + wrong
  const nq = test?.questions.length ?? details.length
  const bl = bands(nq)
  const bandScores = bl.map(([lo, hi]) => ({
    lo,
    hi,
    ok: details.filter((d) => d.n >= lo && d.n <= hi && d.ok).length,
    total: details.filter((d) => d.n >= lo && d.n <= hi).length,
  }))
  return {
    result,
    correct,
    wrong,
    blank,
    answered,
    accuracy: answered ? Math.round((correct / answered) * 100) : 0,
    bandScores,
    missed,
  }
}

/** Knowledge-point accuracy aggregated over every result that has details. */
export function abilityProfile(
  results: TestResult[],
  resolve: KpResolver,
): { kp: string; ok: number; total: number; pct: number }[] {
  const agg = new Map<string, { ok: number; total: number }>()
  for (const r of results) {
    if (!r.details?.length) continue
    for (const d of r.details) {
      const { kp } = resolve(r.test_id, d.n)
      if (!kp || kp === '—') continue
      const a = agg.get(kp) ?? { ok: 0, total: 0 }
      a.total++
      if (d.ok) a.ok++
      agg.set(kp, a)
    }
  }
  return [...agg.entries()]
    .map(([kp, a]) => ({ kp, ...a, pct: a.total ? Math.round((a.ok / a.total) * 100) : 0 }))
    .sort((a, b) => a.pct - b.pct || b.total - a.total)
}

/** All wrong/blank occurrences across results, newest first. */
export function collectMissed(
  results: TestResult[],
  tests: Record<string, AnTest>,
  resolve: KpResolver,
): MissedItem[] {
  const out: MissedItem[] = []
  for (const r of [...results].reverse()) {
    if (!r.details?.length || !tests[r.test_id]) continue
    const byN = new Map(tests[r.test_id].questions.map((q) => [q.n, q]))
    for (const d of r.details) {
      if (d.ok) continue
      const q = byN.get(d.n)
      const { kp, note, diff } = resolve(r.test_id, d.n)
      out.push({
        test_id: r.test_id,
        test_title: r.title,
        submitted_at: r.submitted_at,
        n: d.n,
        given: d.given,
        answer: q?.answer ?? '?',
        kp,
        note,
        diff,
        question: q?.question ?? '',
      })
    }
  }
  return out
}

import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AutoMath } from '../components/AutoMath'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

interface Question {
  n: number
  source?: string
  question: string
  question_zh?: string
  choices?: Record<string, string>
  answer: string
  solution?: string
  solution_zh?: string
  type?: string
  points?: number
}

interface TestData {
  id: string
  title: string
  competition: string
  instructions: string
  time_limit_min: number
  questions: Question[]
}

const fmtTime = (s: number) =>
  `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

/** Legacy difficulty(): olympiad day format (P1 easy, P2–4 medium, P5–6 hard), else by ratio. */
function difficultyClass(n: number, total: number): 'easy' | 'mid' | 'hard' {
  if (total <= 6) {
    if (n <= 1) return 'easy'
    if (n <= 4) return 'mid'
    return 'hard'
  }
  const r = n / total
  if (r <= 0.4) return 'easy'
  if (r <= 0.75) return 'mid'
  return 'hard'
}

/** Legacy grading: exact for choices/integers (leading zeros stripped), 2% tolerance for numeric. */
function grade(q: Question, given: string | undefined): boolean {
  if (q.choices) return given === q.answer
  if (q.type === 'numeric') {
    const g = parseFloat(given ?? '')
    const w = parseFloat(q.answer)
    return !Number.isNaN(g) && !Number.isNaN(w) && Math.abs(g - w) <= Math.max(0.02 * Math.abs(w), 1e-9)
  }
  const g = (given ?? '').replace(/^0+(?=\d)/, '')
  const w = String(q.answer).replace(/^0+(?=\d)/, '')
  return g !== '' && g === w
}

/** Wrap a bare LaTeX fragment in $…$ when it isn't already delimited (legacy choice/answer display). */
function wrapMath(v: string, withCaret = false): string {
  const re = withCaret ? /\\[a-zA-Z]|\^/ : /\\[a-zA-Z]/
  return re.test(v) && !v.includes('$') ? `$${v}$` : v
}

interface QuestionCardProps {
  q: Question
  total: number
  value?: string
  submitted: boolean
  revealed: boolean
  onPick: (n: number, letter: string) => void
  onType: (n: number, value: string) => void
  onReveal: (n: number) => void
}

function QuestionCard({ q, total, value, submitted, revealed, onPick, onType, onReveal }: QuestionCardProps) {
  const { t, lang } = useI18n()
  const cls = difficultyClass(q.n, total)
  const label = t(cls === 'easy' ? 'easy' : cls === 'mid' ? 'medium' : 'hard')
  const points = q.points || 1
  const showSolution = submitted || revealed
  const ok = submitted && grade(q, value)
  const questionHtml = lang === 'zh' && q.question_zh ? q.question_zh : q.question
  const answerHtml = q.answer ? `<b>${t('answer')}: ${wrapMath(q.answer, true)}.</b> ` : ''
  const solutionSrc = lang === 'zh' && q.solution_zh ? q.solution_zh : q.solution
  const solutionHtml = solutionSrc || `<i>${t('noSolution')}</i>`

  return (
    <div className={`card${submitted ? ' submitted' : ''}`}>
      <div className="qhead">
        <span className="qnum">
          {t('problem')} {q.n}
        </span>
        <span style={{ display: 'flex', gap: 6 }}>
          <span className={`diff ${cls}`}>{label}</span>
          <span className="badge">
            {points} {points > 1 ? t('pts') : t('pt')}
          </span>
          <span className="badge">
            {q.type === 'proof' || q.type === 'numeric' ? t('realProblem') : t('modifiedFrom')} {q.source}
          </span>
        </span>
      </div>
      <AutoMath html={questionHtml} className="qtext" />
      {q.type === 'proof' && !showSolution && (
        <button className="btn secondary" type="button" onClick={() => onReveal(q.n)}>
          {t('showSolution')}
        </button>
      )}
      {q.choices ? (
        <div className="choices">
          {Object.entries(q.choices).map(([letter, v]) => {
            const state = submitted
              ? letter === q.answer
                ? ' correct'
                : value === letter
                  ? ' wrong'
                  : ''
              : value === letter
                ? ' selected'
                : ''
            return (
              <div key={letter} className={`choice${state}`} onClick={() => onPick(q.n, letter)}>
                <span className="letter">{letter}</span>
                <AutoMath html={wrapMath(v)} />
              </div>
            )
          })}
        </div>
      ) : q.type === 'proof' ? null : (
        <input
          className={`int-input${submitted ? (ok ? ' correct' : ' wrong') : ''}`}
          type="text"
          inputMode={q.type === 'numeric' ? 'decimal' : 'numeric'}
          maxLength={q.type === 'numeric' ? undefined : 3}
          disabled={submitted}
          value={value ?? ''}
          placeholder={q.type === 'numeric' ? (lang === 'zh' ? '数值答案' : 'number') : '000–999'}
          onChange={(e) => onType(q.n, e.target.value)}
        />
      )}
      {showSolution && <AutoMath className="solution" html={answerHtml + solutionHtml} />}
    </div>
  )
}

/** Exam runner (`/test/:id`) — ports legacy renderTest/pick/typed/submit/exitTest. */
export function TestRunner() {
  const { id = '' } = useParams()
  const { t } = useI18n()
  const navigate = useNavigate()

  const [test, setTest] = useState<TestData | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [submitted, setSubmitted] = useState(false)
  const [result, setResult] = useState<{ score: number; total: number } | null>(null)
  const [savedNote, setSavedNote] = useState<string | null>(null)
  const [revealed, setRevealed] = useState<Set<number>>(new Set())
  const [left, setLeft] = useState(0)

  const deadlineRef = useRef(0)
  const startedAtRef = useRef(0)
  const submittedRef = useRef(false)
  const submitRef = useRef<() => void>(() => {})

  useEffect(() => {
    let alive = true
    api
      .test(id)
      .then((d) => {
        if (!alive) return
        const data = d as TestData
        setTest(data)
        deadlineRef.current = Date.now() + data.time_limit_min * 60000
        startedAtRef.current = Date.now()
        setLeft(data.time_limit_min * 60)
      })
      .catch((e: unknown) => setLoadError(String(e)))
    return () => {
      alive = false
    }
  }, [id])

  function submit() {
    if (!test || submittedRef.current) return
    submittedRef.current = true
    setSubmitted(true)
    let score = 0
    let totalPoints = 0
    for (const q of test.questions) {
      const pts = q.points || 1
      totalPoints += pts
      if (grade(q, answers[q.n])) score += pts
    }
    setResult({ score, total: totalPoints })
    setSavedNote(t('saving'))
    const duration_s = Math.round((Date.now() - startedAtRef.current) / 1000)
    api
      .submitResult({
        test_id: test.id,
        title: test.title,
        competition: test.competition,
        score,
        total: totalPoints,
        answered: Object.keys(answers).length,
        duration_s,
      })
      .then((d) => setSavedNote(d.guest ? t('savedGuest') : t('savedOk')))
      .catch(() => setSavedNote(t('savedFail')))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  useEffect(() => {
    submitRef.current = submit
  })

  useEffect(() => {
    if (!test || submitted) return
    const timerId = setInterval(() => {
      const l = Math.max(0, Math.round((deadlineRef.current - Date.now()) / 1000))
      setLeft(l)
      if (l === 0) submitRef.current()
    }, 1000)
    return () => clearInterval(timerId)
  }, [test, submitted])

  function pick(n: number, letter: string) {
    if (submittedRef.current) return
    setAnswers((a) => ({ ...a, [n]: letter }))
  }

  function type(n: number, value: string) {
    if (submittedRef.current) return
    setAnswers((a) => {
      const next = { ...a }
      if (value.trim() === '') delete next[n]
      else next[n] = value.trim()
      return next
    })
  }

  function reveal(n: number) {
    setRevealed((s) => new Set(s).add(n))
  }

  if (loadError) {
    return (
      <section className="card">
        <p className="status err">API error: {loadError}</p>
        <p style={{ marginTop: 10 }}>
          <Link to="/tests">‹ {t('tabTests')}</Link>
        </p>
      </section>
    )
  }
  if (!test) {
    return (
      <section className="card">
        <p className="muted">{t('loading')}</p>
      </section>
    )
  }

  const total = test.questions.length
  const answeredCount = Object.keys(answers).length
  const scoreText = result
    ? result.total === 0
      ? t('solutionsRevealed')
      : `${t('score')}: ${result.score} / ${result.total}`
    : null

  return (
    <>
      <div className="sticky-bar">
        <div>
          <div style={{ fontWeight: 700 }}>{test.title}</div>
          <div className="progress">
            {answeredCount} / {total} {t('answered')}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          {scoreText && <span className="score">{scoreText}</span>}
          {savedNote && <span className="saved-note">{savedNote}</span>}
          <span className={left < 300 && !submitted ? 'timer low' : 'timer'}>⏱ {fmtTime(left)}</span>
          <button className="btn secondary" type="button" onClick={() => navigate('/tests')}>
            {t('exit')}
          </button>
          <button className="btn" type="button" onClick={submit}>
            {t('submit')}
          </button>
        </div>
      </div>
      <div className="card" style={{ fontSize: 13.5, color: '#555' }}>
        {test.instructions}
      </div>
      {test.questions.map((q) => (
        <QuestionCard
          key={q.n}
          q={q}
          total={total}
          value={answers[q.n]}
          submitted={submitted}
          revealed={revealed.has(q.n)}
          onPick={pick}
          onType={type}
          onReveal={reveal}
        />
      ))}
    </>
  )
}

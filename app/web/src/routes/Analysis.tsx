import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AutoMath } from '../components/AutoMath'
import {
  abilityProfile,
  attemptStats,
  bustClassCache,
  loadAnalysisData,
  loadClassMap,
  loadTest,
  makeKpResolver,
  type AttemptStats,
  type ClassMap,
  type AnTest,
} from '../lib/analysis'
import { api, type Me, type Taxonomy, type TestResult } from '../lib/api'
import { useI18n } from '../lib/i18n'

type SelKey = string // `${test_id}|${submitted_at}`

export function Analysis() {
  const { t, lang } = useI18n()
  const [params] = useSearchParams()
  const [me, setMe] = useState<Me | null>(null)
  const [results, setResults] = useState<TestResult[] | null>(null)
  const [tests, setTests] = useState<Record<string, AnTest>>({})
  const [classes, setClasses] = useState<Record<string, ClassMap>>({})
  const [tax, setTax] = useState<Taxonomy | null>(null)
  const [selected, setSelected] = useState<SelKey[]>([])
  const [clsTest, setClsTest] = useState<string | null>(null) // test being classified
  const [clsList, setClsList] = useState<{ id: string; title: string }[]>([])
  const [clsCustom, setClsCustom] = useState('')
  const [draft, setDraft] = useState<ClassMap>({})
  const [clsMsg, setClsMsg] = useState('')

  useEffect(() => {
    api.me().then((m) => {
      setMe(m)
      if (m.role === 'teacher') {
        api
          .tests()
          .then((list) => setClsList(list as { id: string; title: string }[]))
          .catch(() => {})
      }
    }).catch(() => {})
    api.taxonomy().then(setTax).catch(() => {})
    api
      .results()
      .then(async (rs) => {
        setResults(rs)
        const data = await loadAnalysisData(rs)
        setTests(data.tests)
        setClasses(data.classes)
        // deep link: /analysis?test=<id>&at=<submitted_at>
        const tid = params.get('test')
        const at = params.get('at')
        if (tid) {
          const hit = rs.find((r) => r.test_id === tid && (!at || r.submitted_at === at))
          if (hit) setSelected([`${hit.test_id}|${hit.submitted_at}`])
        }
      })
      .catch(() => setResults([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount
  }, [])

  const withDetails = useMemo(() => (results ?? []).filter((r) => r.details?.length), [results])

  const picked: AttemptStats[] = useMemo(
    () =>
      selected
        .map((key) => {
          const [tid, at] = key.split('|')
          const r = withDetails.find((x) => x.test_id === tid && x.submitted_at === at)
          return r ? attemptStats(r, tests[r.test_id], classes[r.test_id]) : null
        })
        .filter((x): x is AttemptStats => !!x),
    [selected, withDetails, tests, classes],
  )

  const resolve = useMemo(
    () => makeKpResolver(tests, classes, tax, lang),
    [tests, classes, tax, lang],
  )

  const profile = useMemo(
    () => (results ? abilityProfile(results, resolve) : []),
    [results, resolve],
  )
  const strengths = profile.filter((p) => p.pct >= 80 && p.total >= 2)
  const weakness = profile.filter((p) => p.pct < 60)

  function toggle(key: SelKey) {
    setSelected((sel) =>
      sel.includes(key) ? sel.filter((k) => k !== key) : sel.length >= 2 ? [sel[1], key] : [...sel, key],
    )
  }

  // ---- teacher classification editor ----
  const isTeacher = me?.role === 'teacher'
  useEffect(() => {
    if (!clsTest) return
    // make sure the test body is available for the editor table
    loadTest(clsTest)
      .then((t) => setTests((prev) => (prev[clsTest] ? prev : { ...prev, [clsTest]: t })))
      .catch(() => {})
    loadClassMap(clsTest).then((c) => setDraft(JSON.parse(JSON.stringify(c))))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when target changes
  }, [clsTest])

  async function saveClass() {
    if (!clsTest) return
    try {
      await api.classifySave(clsTest, draft)
      bustClassCache(clsTest)
      const fresh = await loadClassMap(clsTest).catch(() => ({}))
      setClasses((c) => ({ ...c, [clsTest]: fresh }))
      setClsMsg(t('anClsSaved'))
    } catch (e) {
      setClsMsg(e instanceof Error ? e.message : String(e))
    }
  }

  if (results === null) return <section className="card"><p className="muted">{t('loading')}</p></section>

  return (
    <div className="an-page">
      <section className="card">
        <h3>{t('anTitle')}</h3>
        {withDetails.length === 0 ? (
          <p className="muted">{t('anNone')}</p>
        ) : (
          <>
            <p className="muted">{t('anPick')}</p>
            <div className="an-picks">
              {[...withDetails].reverse().map((r) => {
                const key = `${r.test_id}|${r.submitted_at}`
                return (
                  <label key={key} className={`an-pick${selected.includes(key) ? ' on' : ''}`}>
                    <input type="checkbox" checked={selected.includes(key)} onChange={() => toggle(key)} />
                    <span>
                      {r.title}
                      <br />
                      <span className="meta">
                        {t('anScore')} {r.score}/{r.total} · {t('anTakenAt', r.submitted_at)}
                      </span>
                    </span>
                  </label>
                )
              })}
            </div>
          </>
        )}
      </section>

      {picked.length > 0 && (
        <>
          {/* 一、成绩总览 */}
          <section className="card an-report">
            <h4>1 · {t('anOverview')}</h4>
            <table className="an-table">
              <thead>
                <tr>
                  <th>{t('anExam')}</th>
                  <th>{t('anScore')}</th>
                  <th>{t('anCorrect')}</th>
                  <th>{t('anWrong')}</th>
                  <th>{t('anBlank')}</th>
                  <th>{t('anAccuracy')}</th>
                </tr>
              </thead>
              <tbody>
                {picked.map((p) => (
                  <tr key={p.result.submitted_at}>
                    <td>{p.result.title}</td>
                    <td>
                      {p.result.score}/{p.result.total}
                    </td>
                    <td>{p.correct}</td>
                    <td>{p.wrong}</td>
                    <td>{p.blank}</td>
                    <td>
                      {p.accuracy}% ({p.correct}/{p.answered})
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {/* 二、分段得分 */}
          <section className="card an-report">
            <h4>2 · {t('anSection')}</h4>
            <table className="an-table">
              <thead>
                <tr>
                  <th>{t('anExam')}</th>
                  {picked[0].bandScores.map((b) => (
                    <th key={b.lo}>
                      {b.lo}–{b.hi}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {picked.map((p) => (
                  <tr key={p.result.submitted_at}>
                    <td>{p.result.title}</td>
                    {p.bandScores.map((b) => (
                      <td key={b.lo}>
                        {b.ok}/{b.total}
                        {b.total > 0 && (
                          <span className="meta"> ({Math.round((b.ok / b.total) * 100)}%)</span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {/* 三、失分明细 */}
          {picked.map((p) => (
            <section key={p.result.submitted_at} className="card an-report">
              <h4>
                3 · {t('anLost')} — {p.result.title}
              </h4>
              {p.missed.length === 0 ? (
                <p className="muted">{t('anNoMistakes')}</p>
              ) : (
                <table className="an-table">
                  <thead>
                    <tr>
                      <th>{t('anQNum')}</th>
                      <th>{t('anKP')}</th>
                      <th>{t('anMyAns')}</th>
                      <th>{t('anRightAns')}</th>
                      <th>{t('anKeyPoint')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.missed.map(({ detail, q }) => {
                      const info = resolve(p.result.test_id, detail.n)
                      return (
                        <tr key={detail.n}>
                          <td>{detail.n}</td>
                          <td>{info.kp}</td>
                          <td>{detail.given || t('anUnanswered')}</td>
                          <td>
                            <AutoMath html={String(q?.answer ?? '')} />
                          </td>
                          <td>{info.note}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </section>
          ))}

          {/* 四、能力画像 */}
          <section className="card an-report">
            <h4>4 · {t('anAbility')}</h4>
            {profile.length === 0 ? (
              <p className="muted">{t('anNoCls')}</p>
            ) : (
              <>
                {strengths.length > 0 && (
                  <p>
                    <b>{t('anStrengths')}:</b>{' '}
                    {strengths.map((s) => `${s.kp} (${s.pct}%)`).join(' · ')}
                  </p>
                )}
                {weakness.length > 0 && (
                  <div className="an-kp-list">
                    <b>{t('anWeakness')}:</b>
                    {weakness.map((w) => (
                      <div key={w.kp} className="an-kp-row">
                        <span className="an-kp-name">{w.kp}</span>
                        <span className="pct-bar">
                          <span style={{ width: `${w.pct}%` }} className={w.pct < 40 ? 'low' : ''} />
                        </span>
                        <span className="meta">
                          {w.ok}/{w.total} · {w.pct}%
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </section>

          {/* 五、提分空间 + 建议 */}
          {picked.length > 0 && (
            <section className="card an-report">
              <h4>5 · {t('anGain')}</h4>
              <ul>
                {(() => {
                  // blanks in the first two bands = cheapest points
                  let cheapPts = 0
                  for (const p of picked) {
                    for (const m of p.missed) {
                      const band = p.bandScores.findIndex((b) => m.detail.n >= b.lo && m.detail.n <= b.hi)
                      if (band <= 1 && !m.detail.given) cheapPts += m.q?.points ?? 1
                    }
                  }
                  return cheapPts > 0 ? <li>{t('anGainBlank', String(cheapPts))}</li> : null
                })()}
                {weakness.length > 0 && (
                  <li>{t('anGainWeak', weakness.slice(0, 3).map((w) => w.kp).join('、'))}</li>
                )}
              </ul>
              <h4>6 · {t('anAdvice')}</h4>
              <ul>
                <li>{t('anAdvice1')}</li>
                {weakness.length > 0 && <li>{t('anAdvice2', weakness.slice(0, 2).map((w) => w.kp).join('、'))}</li>}
                <li>{t('anAdvice3')}</li>
              </ul>
            </section>
          )}
        </>
      )}

      {/* teacher classification editor */}
      {isTeacher && (
        <section className="card">
          <h3>{t('anClassify')}</h3>
          <div className="an-picks">
            {clsList.map((c) => (
              <button
                key={c.id}
                type="button"
                className={clsTest === c.id ? 'btn sm' : 'btn sm ghost'}
                onClick={() => {
                  setClsTest(clsTest === c.id ? null : c.id)
                  setClsMsg('')
                }}
              >
                {c.title}
              </button>
            ))}
          </div>
          <div className="an-cls-actions">
            <input
              placeholder="test id (e.g. amc10_rand_01)"
              value={clsCustom}
              onChange={(e) => setClsCustom(e.target.value)}
              style={{ width: 240 }}
            />
            <button
              type="button"
              className="btn sm"
              onClick={() => {
                const id = clsCustom.trim()
                if (!id) return
                setClsTest(id)
                setClsMsg('')
              }}
            >
              {t('drStart')}
            </button>
          </div>
          {clsTest && !tests[clsTest] && <p className="muted">{t('loading')}</p>}
          {clsTest && tests[clsTest] && (
            <>
              <table className="an-table an-cls-table">
                <thead>
                  <tr>
                    <th>{t('anQNum')}</th>
                    <th>{t('anKp')}</th>
                    <th>{t('anDiff')}</th>
                    <th>{t('anNote')}</th>
                  </tr>
                </thead>
                <tbody>
                  {tests[clsTest].questions.map((q) => {
                    const cur = draft[String(q.n)] ?? {}
                    return (
                      <tr key={q.n}>
                        <td>{q.n}</td>
                        <td>
                          <input
                            value={cur.kp ?? ''}
                            onChange={(e) =>
                              setDraft((d) => ({ ...d, [q.n]: { ...d[String(q.n)], kp: e.target.value } }))
                            }
                          />
                        </td>
                        <td>
                          <select
                            value={cur.diff ?? ''}
                            onChange={(e) =>
                              setDraft((d) => ({
                                ...d,
                                [q.n]: { ...d[String(q.n)], diff: e.target.value ? Number(e.target.value) : undefined },
                              }))
                            }
                          >
                            <option value="">—</option>
                            {[1, 2, 3, 4, 5].map((v) => (
                              <option key={v} value={v}>
                                {v}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <input
                            value={cur.note ?? ''}
                            onChange={(e) =>
                              setDraft((d) => ({ ...d, [q.n]: { ...d[String(q.n)], note: e.target.value } }))
                            }
                          />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <div className="an-cls-actions">
                <button type="button" className="btn" onClick={() => void saveClass()}>
                  {t('anSaveCls')}
                </button>
                {clsMsg && <span className="meta">{clsMsg}</span>}
              </div>
            </>
          )}
        </section>
      )}
    </div>
  )
}

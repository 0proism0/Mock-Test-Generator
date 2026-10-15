import { useEffect, useState } from 'react'
import { api, type ClassInfo, type ClassReport } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

type ReportsState = ClassReport[] | 'loading' | null

function ReportsTable({ reports }: { reports: ClassReport[] }) {
  const { t } = useI18n()
  if (!reports.length) return <p className="muted">{t('clNoReports')}</p>
  return (
    <table className="cl-reports">
      <tbody>
        <tr>
          <th>{t('clDate')}</th>
          <th>{t('clStudent')}</th>
          <th>{t('clTest')}</th>
          <th>{t('clScore')}</th>
          <th>{t('clTime')}</th>
        </tr>
        {reports.map((r, i) => (
          <tr key={`${r.student}-${r.submitted_at}-${i}`}>
            <td>{r.submitted_at || ''}</td>
            <td>
              <b>{r.student}</b>
            </td>
            <td>{r.title || r.test_id || ''}</td>
            <td>{r.pct !== null && r.pct !== undefined ? `${r.pct}%` : `${r.score ?? '—'}/${r.total ?? '?'}`}</td>
            <td>
              {r.duration_s != null
                ? `${Math.floor(r.duration_s / 60)}m${String(r.duration_s % 60).padStart(2, '0')}s`
                : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Legacy "Classes" tab: teacher class creation + student reports, or student join/list. */
export function Classes() {
  const { t } = useI18n()
  const { role } = useAuth()
  const isTeacher = role === 'teacher'
  const [data, setData] = useState<{ teaching: ClassInfo[]; joined: ClassInfo[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadTick, setReloadTick] = useState(0)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [joinCode, setJoinCode] = useState('')
  const [reports, setReports] = useState<Record<string, ReportsState>>({})

  useEffect(() => {
    api
      .classes()
      .then(setData)
      .catch((e: unknown) => setError(String(e)))
  }, [reloadTick])

  async function create() {
    try {
      const d = await api.classCreate(name.trim(), code.trim())
      setMsg({ ok: true, text: `✓ ${d.code}` })
      setName('')
      setCode('')
      setReloadTick((n) => n + 1)
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    }
  }

  async function join() {
    try {
      const d = await api.classJoin(joinCode.trim())
      setMsg({ ok: true, text: `✓ ${d.name} (${d.school})` })
      setJoinCode('')
      setReloadTick((n) => n + 1)
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    }
  }

  async function toggleReports(c: string) {
    if (reports[c]) {
      setReports((r) => ({ ...r, [c]: null }))
      return
    }
    setReports((r) => ({ ...r, [c]: 'loading' }))
    try {
      const d = await api.classReports(c)
      setReports((r) => ({ ...r, [c]: d.reports }))
    } catch {
      setReports((r) => ({ ...r, [c]: [] }))
    }
  }

  if (error) {
    return (
      <section className="card">
        <p className="status err">API error: {error}</p>
      </section>
    )
  }
  if (!data) {
    return (
      <section className="card">
        <p className="muted">{t('loading')}</p>
      </section>
    )
  }

  return (
    <div className="card">
      <h3>{t('tabClasses')}</h3>
      {isTeacher ? (
        <>
          <h4 style={{ margin: '10px 0 6px' }}>{t('clCreate')}</h4>
          <div className="pk-form">
            <input
              type="text"
              placeholder={t('clNamePh')}
              style={{ flex: 1, minWidth: 120 }}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <input
              type="text"
              placeholder={t('clCodePh')}
              style={{ width: 130 }}
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            <button className="btn" type="button" onClick={() => void create()}>
              {t('clCreate')}
            </button>
          </div>
          {msg && <div className={`auth-msg ${msg.ok ? 'ok' : 'err'}`}>{msg.text}</div>}
          <div>
            {data.teaching.length ? (
              data.teaching.map((c) => (
                <div key={c.code} className="card compact" style={{ marginTop: 10 }}>
                  <div className="fr-req">
                    <div>
                      <h3>{c.name}</h3>
                      <div className="meta">
                        {c.school} · {t('clCode')}: <span className="cl-code">{c.code}</span>
                      </div>
                    </div>
                    <button className="btn sm" type="button" onClick={() => void toggleReports(c.code)}>
                      {t('clReports')}
                    </button>
                  </div>
                  <div className="cl-students">
                    {(c.students ?? []).length ? (
                      (c.students ?? []).map((s) => (
                        <span key={s} className="cl-student">
                          {s}
                        </span>
                      ))
                    ) : (
                      <span className="muted">{t('clNoStudents')}</span>
                    )}
                  </div>
                  {reports[c.code] === 'loading' && <p className="muted">{t('loading')}</p>}
                  {Array.isArray(reports[c.code]) && <ReportsTable reports={reports[c.code] as ClassReport[]} />}
                </div>
              ))
            ) : (
              <p className="muted">{t('clNoClassesT')}</p>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="cl-join-box">
            <h4 style={{ margin: '0 0 8px' }}>{t('clJoin')}</h4>
            <div className="pk-form" style={{ margin: 0 }}>
              <input
                type="text"
                placeholder={t('clJoinPh')}
                style={{ width: 200 }}
                autoComplete="off"
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value)}
              />
              <button className="btn" type="button" onClick={() => void join()}>
                {t('clJoin')} →
              </button>
            </div>
            {msg && <div className={`auth-msg ${msg.ok ? 'ok' : 'err'}`}>{msg.text}</div>}
          </div>
          <h4 style={{ margin: '16px 0 6px' }}>{t('tabClasses')}</h4>
          <div>
            {data.joined.length ? (
              data.joined.map((c) => (
                <div key={c.code} className="card compact" style={{ marginTop: 10 }}>
                  <h3>{c.name}</h3>
                  <div className="meta">
                    {t('clSchool')}: {c.school} · {t('clTeacher')}: {c.teacher || '—'}
                  </div>
                </div>
              ))
            ) : (
              <p className="muted">{t('clNone')}</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}

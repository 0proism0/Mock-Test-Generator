import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AutoMath } from '../components/AutoMath'
import { api, type Worksheet as WorksheetData, type WorksheetSummary } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

const MAX_BYTES = 1024 * 1024 // keep in sync with WS_MAX_BYTES in server.py

const EXAMPLE = `1. What is $2x + 3x$ when $x = 4$?
A. 12
B. 20
C. 7

2. Solve: $x^2 = 49$

Answers:
1. B
2. 7`

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result).split(',')[1] ?? '')
    r.onerror = () => reject(new Error('read failed'))
    r.readAsDataURL(file)
  })
}

export function Worksheet() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const [ws, setWs] = useState<WorksheetData | null>(null)
  const [mine, setMine] = useState<WorksheetSummary[] | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showKey, setShowKey] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  function pickFiles(f: FileList | null) {
    setFile(f?.[0] ?? null)
    setError(null)
    if (fileRef.current) fileRef.current.value = '' // allow re-picking the same file
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    pickFiles(e.dataTransfer.files)
  }

  // deep link: /worksheet?id=...
  useEffect(() => {
    const id = params.get('id')
    if (id) {
      api
        .worksheet(id)
        .then(setWs)
        .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount
  }, [])

  // "My worksheets" for logged-in users
  useEffect(() => {
    if (user) {
      api
        .worksheets()
        .then(setMine)
        .catch(() => setMine([]))
    }
  }, [user, ws?.id])

  async function loadById(id: string) {
    setBusy(true)
    setError(null)
    try {
      const w = await api.worksheet(id)
      setWs(w)
      setShowKey(false)
      setParams({ id })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function onGenerate() {
    setError(null)
    if (!file) {
      setError(t('wsNoFile'))
      return
    }
    if (file.size > MAX_BYTES) {
      setError(t('wsTooBig'))
      return
    }
    setBusy(true)
    try {
      const data_b64 = await fileToBase64(file)
      const w = await api.worksheetGenerate({ filename: file.name, data_b64 })
      setWs(w)
      setShowKey(false)
      setParams({ id: w.id })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  function onNew() {
    setWs(null)
    setShowKey(false)
    setFile(null)
    setError(null)
    setParams({})
    if (fileRef.current) fileRef.current.value = ''
  }

  if (ws) {
    return (
      <section className="card">
        <div className="ws-head no-print">
          <button type="button" className="btn sm" onClick={() => window.print()}>
            {t('wsPrint')}
          </button>
          <button type="button" className="btn sm ghost" onClick={() => setShowKey((v) => !v)}>
            {showKey ? t('wsKeyHide') : t('wsKeyShow')}
          </button>
          <button type="button" className="btn sm ghost" onClick={onNew}>
            {t('wsNew')}
          </button>
        </div>
        <h2>{ws.title}</h2>
        <p className="meta">
          {t('wsQuestions', String(ws.questions.length))} · {t('wsPoints', String(ws.total_points))} ·{' '}
          {ws.created_at}
        </p>
        <ol className="ws-questions">
          {ws.questions.map((q) => (
            <li key={q.n} className="ws-q">
              <AutoMath className="ws-q-text" html={q.question} />
              {q.choices.length > 0 && (
                <ol className="ws-choices" type="A">
                  {q.choices.map((c, i) => (
                    <li key={i}>
                      <AutoMath html={c} />
                    </li>
                  ))}
                </ol>
              )}
              {showKey && (
                <p className="ws-ans">
                  <b>{t('wsAnswer')}:</b>{' '}
                  <AutoMath html={q.answer || t('wsMissing')} />
                </p>
              )}
            </li>
          ))}
        </ol>
      </section>
    )
  }

  return (
    <>
      <section
        className={`card ws-drop${dragOver ? ' over' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <h3>{t('tabWorksheet')}</h3>
        <p className="muted">{t('wsDesc')}</p>
        <input
          ref={fileRef}
          id="ws-file"
          type="file"
          accept=".txt,.md,.json"
          className="ws-file-input"
          onChange={(e) => pickFiles(e.target.files)}
        />
        <div className="ws-upload">
          <button type="button" className="btn" disabled={busy} onClick={() => fileRef.current?.click()}>
            {t('wsChoose')}
          </button>
          <span className="muted">
            {file ? `${file.name} · ${Math.round(file.size / 1024)} KB` : t('wsDropHint')}
          </span>
          <button type="button" className="btn" disabled={busy} onClick={() => void onGenerate()}>
            {busy ? t('loading') : t('wsGenerate')}
          </button>
        </div>
        {error && <p className="status err">{error}</p>}
      </section>
      <section className="card">
        <h3>{t('wsHowTo')}</h3>
        <p className="muted">{t('wsHowToTxt')}</p>
        <details>
          <summary>{t('wsExample')}</summary>
          <pre className="ws-example">{EXAMPLE}</pre>
        </details>
      </section>
      {user && (
        <section className="card">
          <h3>{t('wsMine')}</h3>
          {!mine ? (
            <p className="muted">{t('loading')}</p>
          ) : mine.length === 0 ? (
            <p className="muted">{t('wsNoMine')}</p>
          ) : (
            <ul className="ws-mine">
              {mine.map((m) => (
                <li key={m.id}>
                  <button type="button" className="ws-link" disabled={busy} onClick={() => void loadById(m.id)}>
                    {m.title}
                  </button>
                  <span className="meta">
                    {' '}
                    · {t('wsQuestions', String(m.n_questions))} · {m.created_at}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  )
}

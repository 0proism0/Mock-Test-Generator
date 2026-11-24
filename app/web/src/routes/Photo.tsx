import { useEffect, useRef, useState } from 'react'
import { AutoMath } from '../components/AutoMath'
import { Camera, Check, Download, RefreshCw, Upload, XCircle } from '../components/icons'
import { api, type PhotoImportResult, type PhotoOcrResult } from '../lib/api'
import { useI18n } from '../lib/i18n'

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result).split(',')[1] ?? '')
    r.onerror = () => reject(new Error('read failed'))
    r.readAsDataURL(file)
  })
}

function typeLabel(type: string): string {
  return type.replace(/_/g, ' ')
}

type Stage = 'idle' | 'ocr' | 'structure' | 'done'
type Tab = 'blocks' | 'raw' | 'json'

/** Photo of a printed worksheet -> paper JSON (two stages: /api/photo/ocr, /api/photo/structure). */
export function Photo() {
  const { t } = useI18n()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [stage, setStage] = useState<Stage>('idle')
  const [elapsed, setElapsed] = useState(0)
  const [useLlm, setUseLlm] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ocr, setOcr] = useState<PhotoOcrResult | null>(null)
  const [result, setResult] = useState<PhotoImportResult | null>(null)
  const [tab, setTab] = useState<Tab>('blocks')
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const busy = stage === 'ocr' || stage === 'structure'

  // OCR takes ~1 minute; show a live counter so the page does not look frozen.
  useEffect(() => {
    if (!busy) return
    const id = window.setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => window.clearInterval(id)
  }, [busy])

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
  }, [preview])

  function reset() {
    setOcr(null)
    setResult(null)
    setError(null)
    setElapsed(0)
    setStage('idle')
  }

  function pickFiles(list: FileList | null) {
    const f = list?.[0] ?? null
    setFile(f)
    reset()
    if (preview) URL.revokeObjectURL(preview)
    setPreview(f ? URL.createObjectURL(f) : null)
    if (fileRef.current) fileRef.current.value = '' // allow re-picking the same file
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    pickFiles(e.dataTransfer.files)
  }

  async function start() {
    if (!file || busy) return
    reset()
    setStage('ocr')
    try {
      const data_b64 = await fileToBase64(file)
      // stage 1 — as soon as it lands the blocks are on screen
      const page = await api.photoOcr({ filename: file.name, data_b64 })
      setOcr(page)
      setStage('structure')
      // stage 2 — the paper built from those blocks
      const paper = await api.photoStructure({ id: page.id, use_llm: useLlm })
      setResult(paper)
      setStage('done')
      setTab('json')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStage('idle')
    }
  }

  async function restructure() {
    if (!ocr || busy) return
    setStage('structure')
    setError(null)
    try {
      const paper = await api.photoStructure({ id: ocr.id, use_llm: useLlm })
      setResult(paper)
      setStage('done')
      setTab('json')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStage('idle')
    }
  }

  function download() {
    if (!result) return
    const blob = new Blob([JSON.stringify(result.paper, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${result.paper.id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const panelReady = Boolean(ocr || result)

  return (
    <div className="ph-page">
      <h2 className="section-title">
        <Camera size={18} />
        {t('photoTitle')}
      </h2>
      <p className="ph-sub">{t('photoSubtitle')}</p>

      <div className="ph-main">
        <div className="ph-left">
          <section
            className={`card ph-drop${dragOver ? ' over' : ''}${busy ? ' busy' : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => !busy && fileRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') fileRef.current?.click()
            }}
          >
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg"
              className="ph-file"
              onChange={(e) => pickFiles(e.target.files)}
            />
            {preview ? (
              <img className="ph-preview" src={preview} alt={file?.name ?? ''} />
            ) : (
              <div className="ph-placeholder">
                <Upload size={28} />
                <span>{t('photoDrop')}</span>
                <span className="ph-limit">{t('photoLimit')}</span>
              </div>
            )}
          </section>

          <div className="ph-controls">
            <button className="btn" type="button" onClick={() => fileRef.current?.click()} disabled={busy}>
              <Upload size={16} />
              {t('photoPick')}
            </button>
            <label className="ph-toggle">
              <input
                type="checkbox"
                checked={useLlm}
                disabled={busy}
                onChange={(e) => setUseLlm(e.target.checked)}
              />
              <span>{t('photoUseLlm')}</span>
            </label>
            <button className="btn primary" type="button" onClick={start} disabled={!file || busy}>
              {busy ? `${t('photoBusy')} ${elapsed}s` : t('photoStart')}
            </button>
          </div>

          <ol className="ph-steps">
            <li className={stage === 'ocr' ? 'on' : ocr || result ? 'done' : ''}>
              {stage === 'ocr' && <span className="ph-spin" />}
              {(ocr || result) && stage !== 'ocr' && <Check size={14} />}
              {t('photoStepOcr')}
              {ocr && <span className="ph-step-meta">{ocr.count} {t('photoBlockCount')} · {(ocr.ms / 1000).toFixed(1)}s</span>}
            </li>
            <li className={stage === 'structure' ? 'on' : result ? 'done' : ''}>
              {stage === 'structure' && <span className="ph-spin" />}
              {result && <Check size={14} />}
              {t('photoStepStruct')}
              {result && <span className="ph-step-meta">{result.paper.questions.length} {t('photoQuestions')} · {((result.ms ?? 0) / 1000).toFixed(1)}s</span>}
            </li>
          </ol>

          {!panelReady && !busy && <p className="ph-hint">{t('photoTip')}</p>}
          {error && (
            <p className="ph-error">
              <XCircle size={16} />
              {t('photoError')}: {error}
            </p>
          )}
        </div>

        <section className={`card ph-panel${panelReady ? '' : ' empty'}`}>
          <div className="ph-panel-head">
            <h3>{t('photoPanel')}</h3>
            {ocr && (
              <div className="ph-tabs">
                <button type="button" className={tab === 'blocks' ? 'on' : ''} onClick={() => setTab('blocks')}>
                  {t('photoTabBlocks')} ({ocr.count})
                </button>
                <button type="button" className={tab === 'raw' ? 'on' : ''} onClick={() => setTab('raw')}>
                  {t('photoTabRaw')}
                </button>
                <button type="button" className={tab === 'json' ? 'on' : ''} onClick={() => setTab('json')}>
                  {t('photoTabJson')}
                </button>
              </div>
            )}
          </div>

          {!panelReady && (
            <p className="ph-panel-empty">
              {busy ? `${t('photoStepOcr')}… ${elapsed}s` : t('photoPanelEmpty')}
            </p>
          )}

          {ocr && tab === 'blocks' && (
            <ul className="ph-blocks">
              {ocr.blocks.map((b, i) => (
                <li key={i} className={`ph-block k-${b.kind}`}>
                  <span className="ph-block-kind">{b.kind}</span>
                  <span className="ph-block-box">
                    [{b.bbox[0]},{b.bbox[1]},{b.bbox[2]},{b.bbox[3]}]
                  </span>
                  <span className="ph-block-text">{b.text || <i className="ph-none">∅</i>}</span>
                </li>
              ))}
            </ul>
          )}

          {ocr && tab === 'raw' && <pre className="ph-pre">{ocr.raw}</pre>}

          {tab === 'json' && (
            <pre className="ph-pre">
              {result
                ? JSON.stringify(result.paper, null, 2)
                : busy
                  ? `${t('photoStepStruct')}… ${elapsed}s`
                  : t('photoPanelEmpty')}
            </pre>
          )}

          {ocr && !result && !busy && (
            <button className="btn" type="button" onClick={restructure}>
              <RefreshCw size={16} />
              {t('photoRestructure')}
            </button>
          )}
        </section>
      </div>

      {result && (
        <section className="card ph-result">
          <div className="ph-head">
            <div>
              <h3 className="ph-title">{result.paper.title || result.id}</h3>
              <div className="ph-meta">
                <span>
                  {result.paper.questions.length} {t('photoQuestions')}
                </span>
                <span>
                  {result.paper.questions.filter((q) => q.figure?.src).length} {t('photoFigures')}
                </span>
                {result.errors > 0 ? (
                  <span className="ph-bad">
                    <XCircle size={14} /> {result.errors} error
                  </span>
                ) : (
                  <span className="ph-ok">
                    <Check size={14} /> ok
                  </span>
                )}
                {result.warnings > 0 && <span className="ph-warn">{result.warnings} warning</span>}
              </div>
            </div>
            <div className="ph-actions">
              <button className="btn" type="button" onClick={download}>
                <Download size={16} />
                {t('photoDownload')}
              </button>
              <button className="btn" type="button" onClick={() => pickFiles(null)}>
                <Camera size={16} />
                {t('photoAgain')}
              </button>
            </div>
          </div>

          <ol className="ph-list">
            {result.paper.questions.map((q) => (
              <li key={q.n} className="ph-item">
                <div className="ph-item-head">
                  <span className="ph-n">{q.n}</span>
                  <span className="badge">{typeLabel(q.type)}</span>
                  <span className="ph-ans">
                    {t('photoAnswer')}:{' '}
                    {q.answer ? <b>{q.answer}</b> : <i className="ph-none">{t('photoNoAnswer')}</i>}
                  </span>
                </div>
                <div className="ph-stem">
                  <AutoMath html={q.question} />
                </div>
                {q.figure?.src && (
                  <img className="ph-fig" src={q.figure.src} alt={q.figure.alt ?? `figure ${q.n}`} />
                )}
                {q.choices && Object.keys(q.choices).length > 0 && (
                  <ul className="ph-choices">
                    {Object.entries(q.choices).map(([letter, body]) => (
                      <li key={letter}>
                        <span className="ph-letter">{letter}</span>
                        <AutoMath html={body} />
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ol>

          {result.problems.length > 0 && (
            <details className="ph-problems">
              <summary>
                {t('photoProblems')} ({result.problems.length})
              </summary>
              <ul>
                {result.problems.map((p, i) => (
                  <li key={i} className={p.level === 'error' ? 'ph-bad' : 'ph-warn'}>
                    [{p.code}] {p.message}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}
    </div>
  )
}

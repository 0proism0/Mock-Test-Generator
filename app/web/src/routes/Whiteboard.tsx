import katex from 'katex'
import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react'
import { AlertTriangle, Edit3, Keyboard, Plus, X } from '../components/icons'
import { useI18n } from '../lib/i18n'
import { WB_CATS, WB_COLORS } from './whiteboard/data'
import { WB_KEYS, type WbKey } from './whiteboard/keys'

interface Stroke {
  id: number
  erase: boolean
  color: string
  size: number
  pts: { x: number; y: number }[]
}

interface Note {
  id: number
  tex: string
  x: number
  y: number
  z?: number
}

type Action = { t: 'stroke'; id: number } | { t: 'note'; id: number }

const STORAGE_KEY = 'mt_wb'
const PEN_SIZE = 3

/** Legacy WB note rendering: plain text when there is no LaTeX syntax, otherwise KaTeX. */
function isPlain(s: string): boolean {
  return !/[\\^_{}]/.test(s)
}

function Tex({ tex, always = false }: { tex: string; always?: boolean }) {
  const html = useMemo(() => {
    if (!always && isPlain(tex)) return null
    try {
      return katex.renderToString(tex, { throwOnError: false })
    } catch {
      return null
    }
  }, [tex, always])
  if (html === null) return <>{tex}</>
  return <span dangerouslySetInnerHTML={{ __html: html }} />
}

function loadState(): { strokes: Stroke[]; notes: Note[]; seq: number } {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') as
      | { strokes?: Stroke[]; notes?: Note[] }
      | null
    const strokes = raw?.strokes ?? []
    const notes = raw?.notes ?? []
    const seq = Math.max(0, ...strokes.map((s) => s.id || 0), ...notes.map((n) => n.id || 0))
    return { strokes, notes, seq }
  } catch {
    return { strokes: [], notes: [], seq: 0 }
  }
}

/** Legacy "Whiteboard" tab: canvas drawing, a formula library, and draggable LaTeX notes. */
export function Whiteboard() {
  const { t, lang } = useI18n()
  const initial = useMemo(() => loadState(), [])

  const strokesRef = useRef<Stroke[]>(initial.strokes)
  const seqRef = useRef(initial.seq)
  const zRef = useRef(10)
  const actionsRef = useRef<Action[]>([])
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const noteEls = useRef<Map<number, HTMLDivElement>>(new Map())
  const dragRef = useRef<{ id: number; dx: number; dy: number } | null>(null)
  const drawingRef = useRef<Stroke | null>(null)
  const pendingPlaceRef = useRef<number | null>(null)
  const editorTexRef = useRef<HTMLTextAreaElement>(null)
  const notesRef = useRef<Note[]>(initial.notes)

  const [notes, setNotes] = useState<Note[]>(initial.notes)
  const [tool, setTool] = useState<'pen' | 'eraser'>('pen')
  const [color, setColor] = useState(WB_COLORS[0])
  const [grp, setGrp] = useState('MATH')
  const [cat, setCat] = useState('arith')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<{ kind: 'new' } | { kind: 'note'; id: number } | null>(null)
  const [editorText, setEditorText] = useState('')
  const [kbVisible, setKbVisible] = useState(true)
  const [kbTab, setKbTab] = useState('vars')

  const setNotesBoth = (updater: (prev: Note[]) => Note[]) => {
    const next = updater(notesRef.current)
    notesRef.current = next
    setNotes(next)
  }

  function save() {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          strokes: strokesRef.current,
          notes: notesRef.current.map((n) => ({ id: n.id, tex: n.tex, x: n.x, y: n.y })),
        }),
      )
    } catch {
      /* storage full: keep in memory only */
    }
  }

  function drawStroke(ctx: CanvasRenderingContext2D, s: Stroke) {
    if (s.erase) ctx.globalCompositeOperation = 'destination-out'
    ctx.strokeStyle = s.color
    ctx.lineWidth = s.size
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.beginPath()
    s.pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)))
    if (s.pts.length === 1) ctx.lineTo(s.pts[0].x + 0.1, s.pts[0].y)
    ctx.stroke()
    ctx.globalCompositeOperation = 'source-over'
  }

  function redraw() {
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    if (!ctx) return
    ctx.save()
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, cv.width, cv.height)
    ctx.restore()
    for (const s of strokesRef.current) drawStroke(ctx, s)
  }

  function resize() {
    const wrap = wrapRef.current
    const cv = canvasRef.current
    if (!wrap || !cv) return
    const dpr = window.devicePixelRatio || 1
    const w = wrap.clientWidth
    const h = wrap.clientHeight
    if (!w || !h) return
    cv.width = Math.round(w * dpr)
    cv.height = Math.round(h * dpr)
    const ctx = cv.getContext('2d')
    if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    redraw()
  }

  useEffect(() => {
    const wrap = wrapRef.current
    if (!wrap) return
    const ro = new ResizeObserver(() => resize())
    ro.observe(wrap)
    requestAnimationFrame(() => resize())
    return () => ro.disconnect()
  }, [])

  // First free slot for a new note (legacy wbPlaceNote).
  function findFreeSpot(w: number, h: number, excludeId: number): { x: number; y: number } {
    const wrap = wrapRef.current
    const fallback = {
      x: 30 + ((seqRef.current * 37) % 240),
      y: 30 + ((seqRef.current * 37) % 200),
    }
    if (!wrap) return { x: 20, y: 20 }
    const W = wrap.clientWidth
    const H = wrap.clientHeight
    const rects = [...noteEls.current.entries()]
      .filter(([nid]) => nid !== excludeId)
      .map(([, n]) => ({ x: n.offsetLeft, y: n.offsetTop, w: n.offsetWidth, h: n.offsetHeight }))
    for (let y = 20; y + h < H - 12; y += 26) {
      for (let x = 20; x + w < W - 12; x += 26) {
        const hit = rects.some(
          (r) => x < r.x + r.w + 10 && x + w + 10 > r.x && y < r.y + r.h + 10 && y + h + 10 > r.y,
        )
        if (!hit) return { x, y }
      }
    }
    return fallback
  }

  // Place a freshly added note into the first free slot.
  useLayoutEffect(() => {
    const id = pendingPlaceRef.current
    if (id == null) return
    const el = noteEls.current.get(id)
    if (!el) return
    pendingPlaceRef.current = null
    const pos = findFreeSpot(el.offsetWidth || 120, el.offsetHeight || 40, id)
    setNotesBoth((ns) => ns.map((n) => (n.id === id ? { ...n, x: pos.x, y: pos.y } : n)))
    save()
  }, [notes])

  useEffect(() => {
    if (editing && editorTexRef.current) {
      const el = editorTexRef.current
      el.focus()
      el.setSelectionRange(el.value.length, el.value.length)
    }
  }, [editing])

  // ---- canvas drawing ----
  function onCanvasDown(e: ReactPointerEvent<HTMLCanvasElement>) {
    if (editing) return
    const cv = canvasRef.current
    if (!cv) return
    try {
      cv.setPointerCapture(e.pointerId)
    } catch {
      /* synthetic events */
    }
    const r = cv.getBoundingClientRect()
    const s: Stroke = {
      id: ++seqRef.current,
      erase: tool === 'eraser',
      color,
      size: tool === 'eraser' ? PEN_SIZE * 8 : PEN_SIZE,
      pts: [{ x: e.clientX - r.left, y: e.clientY - r.top }],
    }
    strokesRef.current.push(s)
    drawingRef.current = s
    e.preventDefault()
  }

  function onCanvasMove(e: ReactPointerEvent<HTMLCanvasElement>) {
    const s = drawingRef.current
    const cv = canvasRef.current
    if (!s || !cv) return
    const ctx = cv.getContext('2d')
    if (!ctx) return
    const r = cv.getBoundingClientRect()
    const p = { x: e.clientX - r.left, y: e.clientY - r.top }
    const last = s.pts[s.pts.length - 1]
    ctx.save()
    if (s.erase) ctx.globalCompositeOperation = 'destination-out'
    ctx.strokeStyle = s.color
    ctx.lineWidth = s.size
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.beginPath()
    ctx.moveTo(last.x, last.y)
    ctx.lineTo(p.x, p.y)
    ctx.stroke()
    ctx.restore()
    s.pts.push(p)
  }

  function onCanvasUp() {
    const s = drawingRef.current
    if (!s) return
    if (s.pts.length === 1) s.pts.push({ x: s.pts[0].x + 0.1, y: s.pts[0].y })
    actionsRef.current.push({ t: 'stroke', id: s.id })
    drawingRef.current = null
    save()
  }

  // ---- notes ----
  function addNote(tex: string) {
    const id = ++seqRef.current
    actionsRef.current.push({ t: 'note', id })
    pendingPlaceRef.current = id
    setNotesBoth((ns) => [...ns, { id, tex, x: 20, y: 20, z: ++zRef.current }])
  }

  function deleteNote(id: number) {
    noteEls.current.delete(id)
    setNotesBoth((ns) => ns.filter((n) => n.id !== id))
    if (editing?.kind === 'note' && editing.id === id) setEditing(null)
    save()
  }

  function onNoteDown(e: ReactPointerEvent<HTMLDivElement>, note: Note) {
    if ((e.target as HTMLElement).closest('.wb-del, .wb-edit')) return
    if (editing) return
    const el = e.currentTarget
    try {
      el.setPointerCapture(e.pointerId)
    } catch {
      /* synthetic events */
    }
    dragRef.current = { id: note.id, dx: e.clientX - note.x, dy: e.clientY - note.y }
    setNotesBoth((ns) => ns.map((n) => (n.id === note.id ? { ...n, z: ++zRef.current } : n)))
    e.preventDefault()
  }

  function onNoteMove(e: ReactPointerEvent<HTMLDivElement>) {
    const d = dragRef.current
    const wrap = wrapRef.current
    if (!d || !wrap) return
    const el = noteEls.current.get(d.id)
    const w = el?.offsetWidth ?? 0
    const h = el?.offsetHeight ?? 0
    let x = e.clientX - d.dx
    let y = e.clientY - d.dy
    x = Math.max(0, Math.min(x, wrap.clientWidth - w))
    y = Math.max(0, Math.min(y, wrap.clientHeight - h))
    setNotesBoth((ns) => ns.map((n) => (n.id === d.id ? { ...n, x, y } : n)))
  }

  function onNoteUp() {
    if (!dragRef.current) return
    dragRef.current = null
    save()
  }

  // ---- editor ----
  function openEditor(note: Note | null) {
    setEditing(note ? { kind: 'note', id: note.id } : { kind: 'new' })
    setEditorText(note ? note.tex : '')
    setKbVisible(true)
  }

  function saveEditor() {
    const tex = editorText.trim()
    if (!tex) {
      setEditing(null)
      return
    }
    if (editing?.kind === 'new') {
      addNote(tex)
    } else if (editing?.kind === 'note') {
      const id = editing.id
      setNotesBoth((ns) => ns.map((n) => (n.id === id ? { ...n, tex } : n)))
      save()
    }
    setEditing(null)
  }

  function insertKey(k: WbKey) {
    const ta = editorTexRef.current
    if (!ta) return
    const [tex, , off] = k
    const s = ta.selectionStart ?? ta.value.length
    const e = ta.selectionEnd ?? s
    setEditorText(ta.value.slice(0, s) + tex + ta.value.slice(e))
    const pos = s + (off !== undefined ? off : tex.length)
    requestAnimationFrame(() => {
      ta.focus()
      ta.setSelectionRange(pos, pos)
    })
  }

  function undo() {
    const a = actionsRef.current.pop()
    if (!a) return
    if (a.t === 'stroke') {
      strokesRef.current = strokesRef.current.filter((s) => s.id !== a.id)
      redraw()
    } else {
      noteEls.current.delete(a.id)
      setNotesBoth((ns) => ns.filter((n) => n.id !== a.id))
    }
    save()
  }

  function clearAll() {
    strokesRef.current = []
    actionsRef.current = []
    noteEls.current.clear()
    setNotesBoth(() => [])
    redraw()
    save()
  }

  const cats = WB_CATS.filter((c) => (c.grp || 'MATH') === grp)
  const q = search.trim().toLowerCase()
  const norm = (s: string) => s.toLowerCase().replace(/\\/g, '')
  const items: { tex: string; tag: string | null }[] = q
    ? WB_CATS.flatMap((c) => {
        const tag = lang === 'zh' ? c.zhShort || c.zh : c.enShort || c.en
        return c.items.filter((tex) => norm(tex).includes(norm(q))).map((tex) => ({ tex, tag }))
      })
    : (WB_CATS.find((c) => c.id === cat)?.items ?? []).map((tex) => ({ tex, tag: null }))

  // editor preview (legacy wbEdPreview)
  let previewClass = 'wb-ed-prev'
  const editorTrim = editorText.trim()
  let previewNode: ReactNode
  if (!editorTrim) {
    previewNode = <span style={{ color: '#98a2ae', fontSize: 12.5 }}>Preview</span>
  } else if (isPlain(editorTrim)) {
    previewClass += ' plain'
    previewNode = editorTrim
  } else {
    let html: string | null = null
    let errMsg = ''
    try {
      html = katex.renderToString(editorTrim, { throwOnError: true })
    } catch (e) {
      errMsg = String((e as Error).message || e).slice(0, 120)
    }
    if (html !== null) {
      previewNode = <span dangerouslySetInnerHTML={{ __html: html }} />
    } else {
      previewClass += ' err'
      previewNode = (
        <>
          <AlertTriangle size={13} /> {errMsg}
        </>
      )
    }
  }

  const keyGroup = WB_KEYS[kbTab]

  return (
    <div className="wb-layout">
      <div className="card wb-panel">
        <div className="wb-tools">
          <button className={`wb-tool${tool === 'pen' ? ' on' : ''}`} type="button" onClick={() => setTool('pen')}>
            {t('wbPen')}
          </button>
          <button
            className={`wb-tool${tool === 'eraser' ? ' on' : ''}`}
            type="button"
            onClick={() => setTool('eraser')}
          >
            {t('wbEraser')}
          </button>
          {WB_COLORS.map((c) => (
            <span
              key={c}
              className={`wb-color${c === color ? ' on' : ''}`}
              style={{ background: c }}
              onClick={() => {
                setColor(c)
                if (tool === 'eraser') setTool('pen')
              }}
            />
          ))}
          <button className="wb-tool" type="button" onClick={undo}>
            {t('wbUndo')}
          </button>
          <button className="wb-tool" type="button" onClick={clearAll}>
            {t('wbClear')}
          </button>
        </div>

        <div className="wb-grp-row">
          <button
            className={`wb-grp${grp === 'MATH' ? ' on' : ''}`}
            type="button"
            onClick={() => {
              setGrp('MATH')
              setCat('arith')
              setSearch('')
            }}
          >
            {lang === 'zh' ? '数学' : 'MATH'}
          </button>
          <button
            className={`wb-grp${grp === 'PHYSICS' ? ' on' : ''}`}
            type="button"
            onClick={() => {
              setGrp('PHYSICS')
              setCat(WB_CATS.find((c) => c.grp === 'PHYSICS')?.id ?? 'kin')
              setSearch('')
            }}
          >
            {lang === 'zh' ? '物理' : 'PHYSICS'}
          </button>
        </div>

        <div className="wb-sel-row">
          <select
            value={cat}
            onChange={(e) => {
              setCat(e.target.value)
              setSearch('')
            }}
          >
            {cats.map((c) => (
              <option key={c.id} value={c.id}>
                {lang === 'zh' ? c.zh : c.en}
              </option>
            ))}
          </select>
          <input className="wb-search" placeholder={t('wbSearchPh')} value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>

        <div className="wb-items">
          {items.map((it, i) => (
            <button key={`${it.tex}-${i}`} className="wb-item" type="button" onClick={() => addNote(it.tex)}>
              {it.tag && <span className="wb-tag">{it.tag}</span>}
              <Tex tex={it.tex} always />
            </button>
          ))}
        </div>
        <button className="btn sm wb-custom-btn" type="button" onClick={() => openEditor(null)}>
          <Plus size={14} /> {t('wbCustom')}
        </button>
      </div>

      <div className="card wb-board-wrap" ref={wrapRef}>
        <canvas
          className="wb-canvas"
          ref={canvasRef}
          style={{ cursor: tool === 'pen' ? 'crosshair' : 'cell' }}
          onPointerDown={onCanvasDown}
          onPointerMove={onCanvasMove}
          onPointerUp={onCanvasUp}
          onPointerCancel={onCanvasUp}
        />
        {notes.map((n) => (
          <div
            key={n.id}
            ref={(el) => {
              if (el) noteEls.current.set(n.id, el)
              else noteEls.current.delete(n.id)
            }}
            className="wb-note"
            style={{ left: n.x, top: n.y, zIndex: n.z }}
            onPointerDown={(e) => onNoteDown(e, n)}
            onPointerMove={onNoteMove}
            onPointerUp={onNoteUp}
            onDoubleClick={() => openEditor(n)}
          >
            <span className="wb-body">
              <Tex tex={n.tex} />
            </span>
            <span className="wb-del" onClick={() => deleteNote(n.id)}>
              <X size={12} />
            </span>
            <span className="wb-edit" onClick={() => openEditor(n)}>
              <Edit3 size={11} />
            </span>
          </div>
        ))}

        {editing && (
          <div className="wb-editor">
            <div className="wb-ed-row">
              <textarea
                ref={editorTexRef}
                className="wb-ed-tex"
                rows={2}
                spellCheck={false}
                value={editorText}
                onChange={(e) => setEditorText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    e.stopPropagation()
                    setEditing(null)
                  }
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault()
                    saveEditor()
                  }
                }}
              />
              <div className={previewClass}>{previewNode}</div>
            </div>
            <div className={`wb-kb${kbVisible ? '' : ' hidden'}`}>
              <div className="wb-kb-tabs">
                {Object.entries(WB_KEYS).map(([id, g]) => (
                  <button
                    key={id}
                    className={`wb-kb-tab${id === kbTab ? ' on' : ''}`}
                    type="button"
                    onClick={() => setKbTab(id)}
                  >
                    {lang === 'zh' ? g.zh : g.en}
                  </button>
                ))}
              </div>
              <div className="wb-kb-keys">
                {keyGroup.keys.map((k, i) => (
                  <button key={`${k[0]}-${i}`} className="wb-key" type="button" onClick={() => insertKey(k)}>
                    {k[1] || k[0]}
                  </button>
                ))}
              </div>
            </div>
            <div className="wb-ed-btns">
              <button className="btn sm" type="button" onClick={saveEditor}>
                {t('wbSave')}
              </button>
              <button className="btn sm ghost" type="button" onClick={() => setEditing(null)}>
                {t('wbCancel')}
              </button>
              <button className="wb-tool" type="button" onClick={() => setKbVisible((v) => !v)}>
                <Keyboard size={13} /> {t('wbKb')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

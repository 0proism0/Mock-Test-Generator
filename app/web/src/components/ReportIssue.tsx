import { useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { Check, Flag, X } from './icons'

/** Reason codes must match REPORT_REASONS in app/server.py. */
const REASONS = [
  { id: 'wrong_statement', key: 'rpWrongStatement' },
  { id: 'wrong_answer', key: 'rpWrongAnswer' },
  { id: 'wrong_solution', key: 'rpWrongSolution' },
  { id: 'broken_latex', key: 'rpBrokenLatex' },
  { id: 'missing_figure', key: 'rpMissingFigure' },
  { id: 'duplicate_choices', key: 'rpDupChoices' },
  { id: 'not_a_problem', key: 'rpNotProblem' },
  { id: 'other', key: 'rpOther' },
] as const

export interface ReportTarget {
  /** Stable per-question id: the bank qid, or `<source>#<n>` for generated papers. */
  qid: string
  bank?: string
  version?: number
  source?: string
  competition?: string
  /** First 400 chars are stored server-side, to make triage possible offline. */
  question?: string
}

type Status = 'idle' | 'sending' | 'sent' | 'error'

/**
 * "Report a problem" control shown next to a question, both in the bank browser
 * and in the test runner. Collapsed to one button; expands to a reason + note form.
 * Reports land in reports.jsonl (server side, gitignored).
 */
export function ReportIssue({ target, compact = false }: { target: ReportTarget; compact?: boolean }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<string>(REASONS[0].id)
  const [note, setNote] = useState('')
  const [status, setStatus] = useState<Status>('idle')

  const submit = async () => {
    setStatus('sending')
    try {
      await api.report({ ...target, reason, note })
      setStatus('sent')
      setOpen(false)
      setNote('')
    } catch {
      setStatus('error')
    }
  }

  if (status === 'sent') {
    return (
      <span className="rp-done">
        <Check size={13} aria-hidden="true" />
        {t('rpThanks')}
      </span>
    )
  }

  return (
    <span className="rp">
      <button
        type="button"
        className={compact ? 'link rp-open' : 'btn ghost sm rp-open'}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <Flag size={13} aria-hidden="true" />
        {t('rpReport')}
      </button>
      {open && (
        <div className="rp-form">
          <label className="rp-row">
            <span className="muted">{t('rpReason')}</span>
            <select value={reason} onChange={(e) => setReason(e.target.value)}>
              {REASONS.map((r) => (
                <option key={r.id} value={r.id}>
                  {t(r.key)}
                </option>
              ))}
            </select>
          </label>
          <textarea
            className="rp-note"
            value={note}
            maxLength={600}
            placeholder={t('rpNotePlaceholder')}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="rp-actions">
            <button type="button" className="btn sm" disabled={status === 'sending'} onClick={submit}>
              <Flag size={13} aria-hidden="true" />
              {status === 'sending' ? t('rpSending') : t('rpSend')}
            </button>
            <button type="button" className="btn ghost sm" onClick={() => setOpen(false)}>
              <X size={13} aria-hidden="true" />
              {t('rpCancel')}
            </button>
            {status === 'error' && <span className="rp-err">{t('rpError')}</span>}
          </div>
        </div>
      )}
    </span>
  )
}

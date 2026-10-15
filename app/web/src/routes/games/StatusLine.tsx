import type { ReactNode } from 'react'
import { AlertTriangle, Check, Target } from '../../components/icons'

/** Game status line: a Feather icon chosen by tone + the message. */
export function StatusLine({ tone, children }: { tone: 'info' | 'ok' | 'err'; children: ReactNode }) {
  const Icon = tone === 'ok' ? Check : tone === 'err' ? AlertTriangle : Target
  return (
    <div
      className={`auth-msg ${tone === 'err' ? 'err' : 'ok'}`}
      style={{ display: 'flex', alignItems: 'center', gap: 6, minHeight: 20, marginBottom: 8 }}
    >
      <Icon size={14} />
      <span>{children}</span>
    </div>
  )
}

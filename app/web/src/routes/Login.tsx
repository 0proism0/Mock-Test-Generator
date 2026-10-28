import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

/** Login / register — the first real view, exercising the AuthProvider end-to-end. */
export function Login() {
  const { t } = useI18n()
  const { user, ready, login, register } = useAuth()
  const navigate = useNavigate()

  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [role, setRole] = useState<'student' | 'teacher'>('student')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [school, setSchool] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (ready && user) return <Navigate to="/" replace />

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    const needsSchool = mode === 'register' && role === 'teacher'
    if (!username || !password || (mode === 'register' && !confirm) || (needsSchool && !school)) {
      setError(t('authFillAll'))
      return
    }
    if (mode === 'register' && password !== confirm) {
      setError(t('authPassMismatch'))
      return
    }
    setBusy(true)
    try {
      if (mode === 'login') {
        await login(username, password)
      } else {
        await register(username, password, role, needsSchool ? school : undefined)
      }
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card auth-box">
      <h2 style={{ textAlign: 'center', marginBottom: 8 }}>MockTest Maker</h2>
      <p style={{ textAlign: 'center', color: 'var(--ink-2)', fontSize: 14 }}>{t('authRequired')}</p>
      <div className="auth-tabs">
        <div className={mode === 'login' ? 'auth-tab active' : 'auth-tab'} onClick={() => setMode('login')}>
          {t('login')}
        </div>
        <div className={mode === 'register' ? 'auth-tab active' : 'auth-tab'} onClick={() => setMode('register')}>
          {t('register')}
        </div>
      </div>
      {mode === 'register' && (
        <div className="auth-tabs" style={{ marginBottom: 2 }}>
          <div className={role === 'student' ? 'auth-tab active' : 'auth-tab'} onClick={() => setRole('student')}>
            {t('authStudent')}
          </div>
          <div className={role === 'teacher' ? 'auth-tab active' : 'auth-tab'} onClick={() => setRole('teacher')}>
            {t('authTeacher')}
          </div>
        </div>
      )}
      <form className="auth-form" onSubmit={onSubmit}>
        <label>{t('username')}</label>
        <input type="text" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
        <label>{t('password')}</label>
        <input
          type="password"
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {mode === 'register' && (
          <>
            <label>{t('authConfirm')}</label>
            <input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </>
        )}
        {mode === 'register' && role === 'teacher' && (
          <>
            <label>{t('school')}</label>
            <input type="text" value={school} onChange={(e) => setSchool(e.target.value)} />
          </>
        )}
        <button type="submit" className="btn" disabled={busy}>
          {mode === 'login' ? t('login') : t('register')}
        </button>
      </form>
      <div className="auth-msg err">{error}</div>
    </div>
  )
}

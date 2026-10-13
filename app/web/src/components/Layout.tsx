import { Suspense, type ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { RouteFallback } from './RouteFallback'
import {
  BarChart2,
  Edit3,
  FileText,
  Gamepad2,
  LogIn,
  LogOut,
  PlusSquare,
  School,
  Swords,
  Users,
} from './icons'

interface Tab {
  to: string
  labelKey: string
  icon: ReactNode
  end?: boolean
  /** Hidden until signed in (mirrors the legacy tab bar). */
  authOnly?: boolean
}

const tabs: Tab[] = [
  { to: '/', labelKey: 'tabNew', icon: <PlusSquare size={18} />, end: true },
  { to: '/tests', labelKey: 'tabTests', icon: <FileText size={18} /> },
  { to: '/stats', labelKey: 'tabStats', icon: <BarChart2 size={18} /> },
  { to: '/whiteboard', labelKey: 'tabWhiteboard', icon: <Edit3 size={18} /> },
  { to: '/games', labelKey: 'tabGames', icon: <Gamepad2 size={18} /> },
  { to: '/friends', labelKey: 'tabFriends', icon: <Users size={18} />, authOnly: true },
  { to: '/pk', labelKey: 'tabPK', icon: <Swords size={18} />, authOnly: true },
  { to: '/classes', labelKey: 'tabClasses', icon: <School size={18} />, authOnly: true },
]

export function Layout() {
  const { t, tip, lang, setLang } = useI18n()
  const { user, ready, logout } = useAuth()
  const visible = tabs.filter((tab) => !tab.authOnly || user)

  return (
    <>
      <header className="top">
        <div className="container" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div>
            <h1 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Edit3 size={20} />
              MockTest Maker
            </h1>
            <p>{t('headerSubtitle')}</p>
          </div>
          <div className="user-area">
            {ready &&
              (user ? (
                <>
                  <span className="user-name">{user}</span>
                  <button type="button" className="link" onClick={() => void logout()}>
                    <LogOut size={14} />
                    {t('logout')}
                  </button>
                </>
              ) : (
                <NavLink to="/login" className="link">
                  <LogIn size={14} />
                  {t('login')}
                </NavLink>
              ))}
          </div>
        </div>
      </header>
      <nav className="tabs">
        {visible.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end ?? false}
            className={({ isActive }) => (isActive ? 'active' : '')}
          >
            {tab.icon}
            <span>{tip(tab.labelKey)}</span>
          </NavLink>
        ))}
        <div className="lang-toggle">
          <span role="button" tabIndex={0} className={lang === 'en' ? 'on' : ''} onClick={() => setLang('en')}>
            EN
          </span>
          <span role="button" tabIndex={0} className={lang === 'zh' ? 'on' : ''} onClick={() => setLang('zh')}>
            中文
          </span>
        </div>
      </nav>
      <main className="container">
        <Suspense fallback={<RouteFallback />}>
          <Outlet />
        </Suspense>
      </main>
    </>
  )
}

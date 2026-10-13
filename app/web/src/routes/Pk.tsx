import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Clock, Flag, Swords } from '../components/icons'
import { api, type Bank, type Friend, type PkDuel, type PkGame, type PkRace } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

type PkMode = 'duel' | 'race'

const DIFFS = ['easy', 'medium', 'hard'] as const

function fmtDur(s: number | null | undefined): string {
  return s == null ? '—' : `${Math.floor(s / 60)}m${String(s % 60).padStart(2, '0')}s`
}

/** Legacy "PK" tab: 1v1 duels + multiplayer races, polling active games every 5s. */
export function Pk() {
  const { t, tip } = useI18n()
  const { user } = useAuth()
  const navigate = useNavigate()

  const [friends, setFriends] = useState<Friend[]>([])
  const [comps, setComps] = useState<Bank[]>([])
  const [games, setGames] = useState<PkGame[]>([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<PkMode>('duel')
  const [duelFriend, setDuelFriend] = useState('')
  const [duelComp, setDuelComp] = useState('')
  const [duelDiff, setDuelDiff] = useState('medium')
  const [raceSel, setRaceSel] = useState<Record<string, boolean>>({})
  const [raceComp, setRaceComp] = useState('')
  const [raceDiff, setRaceDiff] = useState('medium')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    Promise.all([api.friends(), api.banks(), api.pk()])
      .then(([fr, bk, pk]) => {
        setFriends(fr.friends)
        setComps(bk.filter((b) => !b.round))
        setGames(pk.games)
        setLoaded(true)
      })
      .catch((e: unknown) => setError(String(e)))
  }, [])

  const hasActive = games.some((g) => g.status === 'active' || g.status === 'submitted')
  useEffect(() => {
    if (!hasActive) return
    const id = setInterval(() => {
      api
        .pk()
        .then((d) => setGames(d.games))
        .catch(() => {})
    }, 5000)
    return () => clearInterval(id)
  }, [hasActive])

  const duelFriendValue = duelFriend || friends[0]?.username || ''
  const duelCompValue = duelComp || comps[0]?.slug || ''
  const raceCompValue = raceComp || comps[0]?.slug || ''

  const compName = (slug: string) => comps.find((c) => c.slug === slug)?.name || slug
  const diffName = (d: string) => t(d === 'easy' ? 'easy' : d === 'hard' ? 'hard' : 'medium')

  async function reload() {
    try {
      setGames((await api.pk()).games)
    } catch {
      /* ignore */
    }
  }

  async function challenge() {
    setMsg(null)
    try {
      if (mode === 'race') {
        const opponents = Object.keys(raceSel).filter((u) => raceSel[u])
        if (!opponents.length) {
          setMsg({ ok: false, text: t('pkPickFriends') })
          return
        }
        await api.pkChallenge({ mode: 'race', opponents, slug: raceCompValue, difficulty: raceDiff })
      } else {
        await api.pkChallenge({ mode: 'duel', opponent: duelFriendValue, slug: duelCompValue, difficulty: duelDiff })
      }
      setMsg({ ok: true, text: t('requestSent') })
      await reload()
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    }
  }

  async function respond(id: string, accept: boolean) {
    try {
      await api.pkRespond(id, accept)
    } catch {
      /* ignore */
    }
    await reload()
  }

  async function start(id: string) {
    try {
      const d = await api.pkStart(id)
      if (d.test_id) {
        navigate(`/test/${d.test_id}`)
        return
      }
    } catch {
      /* fall through to reload */
    }
    await reload()
  }

  function scoreLine(g: PkDuel) {
    const ms = g.my.done ? `${g.my.score}/${g.my.total}` : '—'
    const ts = g.their.done ? `${g.their.score}/${g.their.total}` : g.status === 'active' ? t('pkInProgress') : '—'
    return `${t('pkYou')} ${ms} : ${ts} ${g.opponent}`
  }

  function duelButtons(g: PkDuel): ReactNode {
    if (g.status === 'pending') {
      return g.role === 'opponent' ? (
        <>
          <button className="btn sm" type="button" onClick={() => void respond(g.id, true)}>
            {t('pkAccept')}
          </button>{' '}
          <button className="btn sm ghost" type="button" onClick={() => void respond(g.id, false)}>
            {t('pkDecline')}
          </button>
        </>
      ) : (
        <Clock size={14} />
      )
    }
    if (g.status === 'active') {
      return (
        <button className="btn sm" type="button" onClick={() => navigate(`/test/${g.test_id}`)}>
          {t('pkTakeTest')}
        </button>
      )
    }
    if (g.status === 'submitted') {
      return (
        <span className="pk-muted">
          <Clock size={13} /> {t('pkInProgress')}
        </span>
      )
    }
    return null
  }

  function resultBadge(g: PkDuel): ReactNode {
    if (g.status === 'declined') return <span className="pk-muted">{t('pkDeclined')}</span>
    if (g.status === 'expired') return <span className="pk-muted">{t('pkExpired')}</span>
    if (g.status === 'done') {
      const w =
        g.winner === 'me' ? (
          <span className="pk-won">{t('pkWon')}</span>
        ) : g.winner === 'them' ? (
          <span className="pk-lost">{t('pkLost')}</span>
        ) : (
          <span>{t('pkDraw')}</span>
        )
      return (
        <>
          {w} · {scoreLine(g)}
        </>
      )
    }
    return scoreLine(g)
  }

  function duelRow(g: PkDuel) {
    return (
      <div className="fr-req pk-row" key={g.id}>
        <span>
          <b>{g.opponent}</b> · {compName(g.slug)} · {diffName(g.difficulty)}
          <br />
          <small>{resultBadge(g)}</small>
        </span>
        <span>{duelButtons(g)}</span>
      </div>
    )
  }

  function raceRow(g: PkRace) {
    const standings = g.standings ?? []
    let btn: ReactNode = null
    if (g.status === 'pending') {
      btn = g.is_host ? (
        <button className="btn sm" type="button" disabled={g.accepted.length < 2} onClick={() => void start(g.id)}>
          {t('pkStartRace')}
        </button>
      ) : (
        <>
          <button className="btn sm" type="button" onClick={() => void respond(g.id, true)}>
            {t('pkAccept')}
          </button>{' '}
          <button className="btn sm ghost" type="button" onClick={() => void respond(g.id, false)}>
            {t('pkDecline')}
          </button>
        </>
      )
    } else if (g.status === 'active') {
      const meDone = standings.find((s) => s.user === user && s.done)
      btn = meDone ? (
        <Check size={16} color="#237a23" />
      ) : (
        <button className="btn sm" type="button" onClick={() => navigate(`/test/${g.test_id}`)}>
          {t('pkTakeTest')}
        </button>
      )
    }
    return (
      <div className="card compact" key={g.id} style={{ marginTop: 8 }}>
        <div className="fr-req">
          <span>
            <b>
              <Flag size={14} /> {t('pkRace')}
            </b>{' '}
            · {compName(g.slug)} · {diffName(g.difficulty)}
            {g.is_host ? (
              <>
                {' '}
                · <small>{t('pkHost')}</small>
              </>
            ) : null}
          </span>
          <span>{btn}</span>
        </div>
        <div style={{ fontSize: 13, color: '#666', margin: '4px 0' }}>
          {t('pkJoined')}: {g.accepted.length}/{g.players.length} — {g.accepted.join(', ')}
          {g.invited.length ? (
            <>
              {' '}
              · {t('pkWaiting')}: {g.invited.join(', ')}
            </>
          ) : null}
        </div>
        {g.status === 'done' && g.winner ? (
          <div style={{ fontSize: 13.5, margin: '2px 0' }}>
            {t('pkRaceWinner')}: <b>{g.winner}</b>
          </div>
        ) : null}
        {standings.length ? (
          <div style={{ marginTop: 4 }}>
            {standings.map((s, i) => (
              <div className="pk-stand-row" key={s.user}>
                <span>
                  {i + 1}. <b>{s.user}</b>
                  {s.user === user ? (
                    <>
                      {' '}
                      <small>({t('pkYou')})</small>
                    </>
                  ) : null}
                </span>
                <span>
                  {s.done ? (
                    <>
                      <b>
                        {s.score}/{s.total}
                      </b>{' '}
                      · {fmtDur(s.duration_s)}
                    </>
                  ) : (
                    <small className="pk-muted">{t('pkInProgress')}</small>
                  )}
                </span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    )
  }

  if (error) {
    return (
      <section className="card">
        <p className="status err">API error: {error}</p>
      </section>
    )
  }
  if (!loaded) {
    return (
      <section className="card">
        <p className="muted">{t('loading')}</p>
      </section>
    )
  }

  const duels = games.filter((g): g is PkDuel => g.mode !== 'race')
  const races = games.filter((g): g is PkRace => g.mode === 'race')
  const pendingIn = [
    ...duels.filter((g) => g.status === 'pending' && g.role === 'opponent'),
    ...races.filter((g) => g.status === 'pending' && !g.is_host),
  ]
  const pendingOut = [
    ...duels.filter((g) => g.status === 'pending' && g.role === 'challenger'),
    ...races.filter((g) => g.status === 'pending' && g.is_host),
  ]
  const active = games.filter((g) => g.status === 'active' || g.status === 'submitted')
  const history = games.filter((g) => ['done', 'declined', 'expired'].includes(g.status))
  const rowOf = (g: PkGame) => (g.mode === 'race' ? raceRow(g) : duelRow(g))

  return (
    <div className="card">
      <h3>{t('tabPK')}</h3>
      <div className="pk-mode-tabs">
        <div className={`pk-mode-tab${mode === 'duel' ? ' on' : ''}`} onClick={() => setMode('duel')}>
          <Swords size={15} />
          {tip('pkModeDuel')}
        </div>
        <div className={`pk-mode-tab${mode === 'race' ? ' on' : ''}`} onClick={() => setMode('race')}>
          <Flag size={15} />
          {tip('pkModeRace')}
        </div>
      </div>

      {mode === 'duel' && (
        <div className="pk-form">
          <select value={duelFriendValue} onChange={(e) => setDuelFriend(e.target.value)}>
            {friends.map((f) => (
              <option key={f.username} value={f.username}>
                {f.username}
              </option>
            ))}
          </select>
          <select value={duelCompValue} onChange={(e) => setDuelComp(e.target.value)}>
            {comps.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.name}
              </option>
            ))}
          </select>
          <select value={duelDiff} onChange={(e) => setDuelDiff(e.target.value)}>
            {DIFFS.map((d) => (
              <option key={d} value={d}>
                {diffName(d)}
              </option>
            ))}
          </select>
          <button className="btn" type="button" disabled={!friends.length} onClick={() => void challenge()}>
            {t('pkSend')}
          </button>
        </div>
      )}

      {mode === 'race' && (
        <>
          <div style={{ fontSize: 13, color: '#666', marginBottom: 4 }}>{t('pkPickFriends')}</div>
          <div className="race-friends">
            {friends.length ? (
              friends.map((f) => (
                <label key={f.username} className="race-friend">
                  <input
                    type="checkbox"
                    checked={!!raceSel[f.username]}
                    onChange={(e) => setRaceSel((s) => ({ ...s, [f.username]: e.target.checked }))}
                  />
                  {f.username}
                  {f.online ? <span className="dot on" /> : null}
                </label>
              ))
            ) : (
              <span className="pk-muted">{t('pkNoFriends')}</span>
            )}
          </div>
          <div className="pk-form">
            <select value={raceCompValue} onChange={(e) => setRaceComp(e.target.value)}>
              {comps.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.name}
                </option>
              ))}
            </select>
            <select value={raceDiff} onChange={(e) => setRaceDiff(e.target.value)}>
              {DIFFS.map((d) => (
                <option key={d} value={d}>
                  {diffName(d)}
                </option>
              ))}
            </select>
            <button className="btn" type="button" disabled={!friends.length} onClick={() => void challenge()}>
              <Flag size={14} /> {t('pkInvite')}
            </button>
          </div>
        </>
      )}

      {!friends.length && <p className="pk-muted">{t('pkNoFriends')}</p>}
      {msg && <div className={`auth-msg ${msg.ok ? 'ok' : 'err'}`}>{msg.text}</div>}

      {pendingIn.length > 0 && (
        <>
          <h4 style={{ margin: '14px 0 6px' }}>{t('pkIncoming')}</h4>
          {pendingIn.map(rowOf)}
        </>
      )}
      {pendingOut.length > 0 && (
        <>
          <h4 style={{ margin: '14px 0 6px' }}>{t('pkOutgoing')}</h4>
          {pendingOut.map(rowOf)}
        </>
      )}
      {active.length > 0 && (
        <>
          <h4 style={{ margin: '14px 0 6px' }}>{t('pkActive')}</h4>
          {active.map(rowOf)}
        </>
      )}
      {history.length > 0 && (
        <>
          <h4 style={{ margin: '14px 0 6px' }}>{t('pkHistory')}</h4>
          {history.map(rowOf)}
        </>
      )}
    </div>
  )
}

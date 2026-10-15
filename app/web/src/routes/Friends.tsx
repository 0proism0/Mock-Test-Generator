import { useEffect, useRef, useState } from 'react'
import { api, type ChatMessage, type FriendsData } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { X } from '../components/icons'

/** Legacy "Friends" tab: friend requests, friend list, and a 3s-polled chat. */
export function Friends() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [data, setData] = useState<FriendsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadTick, setReloadTick] = useState(0)
  const [addName, setAddName] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [chatWith, setChatWith] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [online, setOnline] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const sinceRef = useRef(0)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api
      .friends()
      .then(setData)
      .catch((e: unknown) => setError(String(e)))
  }, [reloadTick])

  // Poll the open conversation every 3s (legacy pollChat).
  useEffect(() => {
    if (!chatWith) return
    let alive = true
    const poll = () =>
      api
        .chat(chatWith, sinceRef.current)
        .then((d) => {
          if (!alive) return
          setOnline(d.online)
          if (d.messages.length) {
            for (const m of d.messages) sinceRef.current = Math.max(sinceRef.current, m.ts)
            setMessages((prev) => [...prev, ...d.messages])
          }
        })
        .catch(() => {
          /* transient network error; keep polling */
        })
    void poll()
    const id = setInterval(poll, 3000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [chatWith])

  useEffect(() => {
    const box = scrollRef.current
    if (box) box.scrollTop = box.scrollHeight
  }, [messages])

  function openChat(username: string) {
    setChatWith(username)
    setMessages([])
    setOnline(false)
    sinceRef.current = 0
  }

  async function addFriend() {
    const username = addName.trim().toLowerCase()
    if (!username) return
    try {
      await api.friendAction('request', username)
      setMsg({ ok: true, text: t('requestSent') })
      setAddName('')
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    }
  }

  async function action(kind: 'accept' | 'decline' | 'remove', username: string) {
    try {
      await api.friendAction(kind, username)
    } catch {
      /* ignore */
    }
    if (kind === 'remove' && chatWith === username) setChatWith(null)
    setReloadTick((n) => n + 1)
  }

  async function send() {
    const text = chatInput.trim()
    if (!text || !chatWith) return
    setChatInput('')
    try {
      const d = await api.chatSend(chatWith, text)
      sinceRef.current = Math.max(sinceRef.current, d.message.ts)
      setMessages((prev) => [...prev, d.message])
    } catch {
      setChatInput(text)
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
    <div className="fr-layout">
      <div className="card">
        <h3>{t('tabFriends')}</h3>
        <div className="fr-add">
          <input
            type="text"
            placeholder="username"
            value={addName}
            onChange={(e) => setAddName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void addFriend()
            }}
          />
          <button className="btn" type="button" onClick={() => void addFriend()}>
            {t('addFriend')}
          </button>
        </div>
        {msg && <div className={`auth-msg ${msg.ok ? 'ok' : 'err'}`}>{msg.text}</div>}
        {data.incoming.length > 0 && (
          <>
            <h4 style={{ margin: '12px 0 6px' }}>{t('friendRequests')}</h4>
            {data.incoming.map((u) => (
              <div key={u} className="fr-req">
                <span>{u}</span>
                <span>
                  <button className="btn sm" type="button" onClick={() => void action('accept', u)}>
                    {t('accept')}
                  </button>{' '}
                  <button className="btn sm ghost" type="button" onClick={() => void action('decline', u)}>
                    {t('decline')}
                  </button>
                </span>
              </div>
            ))}
          </>
        )}
        <div style={{ marginTop: 10 }}>
          {data.friends.length ? (
            data.friends.map((f) => (
              <div
                key={f.username}
                className={`fr-item${chatWith === f.username ? ' active' : ''}`}
                onClick={() => openChat(f.username)}
              >
                <span className={`dot${f.online ? ' on' : ''}`} />
                <span className="fr-name">{f.username}</span>
                <span className="fr-status">{f.online ? t('online') : t('offline')}</span>
                <span
                  className="fr-x"
                  title={t('remove')}
                  onClick={(e) => {
                    e.stopPropagation()
                    void action('remove', f.username)
                  }}
                >
                  <X size={14} />
                </span>
              </div>
            ))
          ) : (
            <p className="muted">{t('noFriends')}</p>
          )}
        </div>
      </div>
      <div className="card chat-card">
        {chatWith ? (
          <>
            <div className="chat-head">
              <span className={`dot${online ? ' on' : ''}`} />
              <b>{chatWith}</b>
            </div>
            <div className="chat-msgs" ref={scrollRef}>
              {messages.map((m, i) => (
                <div key={`${m.ts}-${i}`} className={`chat-row${m.frm === user ? ' mine' : ''}`}>
                  <div className="bubble">{m.text}</div>
                </div>
              ))}
            </div>
            <div className="chat-input">
              <input
                type="text"
                placeholder={t('typeMessage')}
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void send()
                }}
              />
              <button className="btn" type="button" onClick={() => void send()}>
                {t('send')}
              </button>
            </div>
          </>
        ) : (
          <p className="muted">{t('selectFriend')}</p>
        )}
      </div>
    </div>
  )
}

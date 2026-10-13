// Same-origin JSON API client for app/server.py.
// In dev, Vite proxies /api to the stdlib Python server (see vite.config.ts).
// In prod, the Python server serves both this SPA and the /api routes.
//
// Views should call these functions instead of using fetch() directly.

export interface Me {
  user: string | null
  role?: string
  school?: string
}

export interface Bank {
  slug: string
  /** null for single-round competitions; otherwise the round name. */
  round: string | null
  name: string
  category?: string
  family?: string
  n_questions: number
  time_limit_min?: number
  ready?: boolean
  total_variants?: number
  positions_covered?: number
  tests_remaining?: number
  tests_total?: number
  real?: boolean
}

export interface TestSummary {
  id: string
  title: string
  competition: string
  n_questions: number
  time_limit_min?: number | null
}

export interface Announcement {
  title?: string
  date?: string
  body?: string
}

export interface TestResult {
  test_id: string
  title: string
  competition: string
  score: number
  total: number
  answered: number
  duration_s?: number
  submitted_at: string
  user: string
}

export interface Friend {
  username: string
  online: boolean
}

export interface FriendsData {
  friends: Friend[]
  incoming: string[]
  outgoing: string[]
}

export interface ChatMessage {
  ts: number
  frm: string
  text: string
}

export interface PkScore {
  done: boolean
  score: number | null
  total: number | null
  answered: number
}

/** 1v1 duel view (server pk_game_view). */
export interface PkDuel {
  id: string
  mode?: 'duel'
  opponent: string
  me: string
  role: 'challenger' | 'opponent'
  slug: string
  difficulty: string
  status: string
  created_at?: string
  test_id?: string
  my: PkScore
  their: PkScore
  winner?: 'me' | 'them' | 'draw'
}

export interface PkStanding {
  user: string
  done: boolean
  score: number | null
  total: number | null
  duration_s: number | null
  answered: number
}

/** Race view (server pk_race_view). */
export interface PkRace {
  id: string
  mode: 'race'
  host: string
  me: string
  is_host: boolean
  slug: string
  difficulty: string
  status: string
  created_at?: string
  test_id?: string
  players: string[]
  accepted: string[]
  invited: string[]
  standings: PkStanding[]
  winner: string | null
}

export type PkGame = PkDuel | PkRace

export interface ClassInfo {
  code: string
  name: string
  school?: string
  teacher?: string
  students?: string[]
}

export interface ClassReport {
  class_id: string
  student: string
  test_id: string
  title: string
  competition: string
  score: number
  total: number
  pct: number | null
  answered: number
  duration_s?: number
  submitted_at: string
}

/** Thrown for any non-2xx response; `status` mirrors the HTTP code, message is the server's `error`. */
export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface RequestOptions {
  method?: string
  body?: unknown
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await fetch(path, {
    method: opts.method ?? 'GET',
    credentials: 'same-origin',
    headers: opts.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  })
  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!res.ok) {
    const message =
      data && typeof data === 'object' && 'error' in data
        ? String((data as { error: unknown }).error)
        : `${res.status} ${res.statusText}`
    throw new ApiError(res.status, message)
  }
  return data as T
}

const post = <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body })

export const api = {
  // identity
  me: () => request<Me>('/api/me'),
  login: (username: string, password: string) =>
    post<{ ok: boolean; user: string }>('/api/login', { username, password }),
  register: (username: string, password: string, role: string, school?: string) =>
    post<{ ok: boolean; user: string }>(
      '/api/register',
      school ? { username, password, role, school } : { username, password, role },
    ),
  logout: () => post<{ ok: boolean }>('/api/logout'),

  // banks / tests / results
  banks: () => request<Bank[]>('/api/banks'),
  tests: () => request<TestSummary[]>('/api/tests'),
  test: (id: string) => request<unknown>(`/api/test/${id}`),
  generate: (slug: string, round?: string | null) =>
    request<{ ok: boolean; id: string }>(`/api/generate/${slug}${round ? `/${encodeURIComponent(round)}` : ''}`),
  results: () => request<TestResult[]>('/api/results'),
  stats: () => request<unknown>('/api/stats'),
  submitResult: (payload: {
    test_id: string
    title: string
    competition: string
    score: number
    total: number
    answered: number
    duration_s: number
  }) => post<{ ok: boolean; guest?: boolean }>('/api/result', payload),
  announcements: () => request<{ announcements: Announcement[] }>('/api/announcements'),

  // friends / chat
  friends: () => request<FriendsData>('/api/friends'),
  friendsBadge: () => request<{ count: number }>('/api/friends/badge'),
  friendAction: (action: 'request' | 'accept' | 'decline' | 'remove', username: string) =>
    post<{ ok: boolean }>(`/api/friends/${action}`, { username }),
  chat: (username: string, since = 0) =>
    request<{ messages: ChatMessage[]; online: boolean }>(`/api/chat/${username}?since=${since}`),
  chatSend: (username: string, text: string) =>
    post<{ ok: boolean; message: ChatMessage }>(`/api/chat/${username}`, { text }),

  // pk battles
  pk: () => request<{ games: PkGame[]; levels: string[] }>('/api/pk'),
  pkInvites: () => request<{ count: number; invites: unknown[] }>('/api/pk/invites'),
  pkGame: (id: string) => request<unknown>(`/api/pk/${id}`),
  pkChallenge: (payload: {
    mode: 'duel' | 'race'
    slug: string
    difficulty: string
    opponent?: string
    opponents?: string[]
  }) => post<{ ok: boolean; id: string }>('/api/pk/challenge', payload),
  pkRespond: (game_id: string, accept: boolean) =>
    post<{ ok: boolean; test_id?: string }>('/api/pk/respond', { game_id, accept }),
  pkStart: (game_id: string) => post<{ ok: boolean; test_id: string }>('/api/pk/start', { game_id }),

  // classes
  classes: () => request<{ teaching: ClassInfo[]; joined: ClassInfo[] }>('/api/classes'),
  classCreate: (name: string, code: string) => post<{ ok: boolean; code: string }>('/api/class/create', { name, code }),
  classJoin: (code: string) => post<{ ok: boolean; name: string; school: string }>('/api/class/join', { code }),
  classReports: (code: string) => request<{ reports: ClassReport[] }>(`/api/class/${code}/reports`),
}

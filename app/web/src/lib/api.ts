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
  /** Bank versions this competition can be generated from (1 = classic, 2 = figure bank). */
  versions?: number[]
  /** Eligible questions in the figure bank (0 when that bank is not installed). */
  v2_variants?: number
  /** How many of those questions carry a figure. */
  v2_figures?: number
}

export interface TestSummary {
  id: string
  title: string
  competition: string
  n_questions: number
  time_limit_min?: number | null
}

export interface WorksheetQuestion {
  n: number
  question: string
  choices: string[]
  answer: string
  solution: string
  points: number
}

export interface Worksheet {
  id: string
  title: string
  owner: string
  created_at: string
  questions: WorksheetQuestion[]
  total_points: number
}

export interface WorksheetSummary {
  id: string
  title: string
  n_questions: number
  created_at: string
}

export interface PracticeLevelStats {
  best_pct: number
  best_time: number | null
  sessions: number
  streak: number
}

export type PracticeStats = Record<string, Record<string, PracticeLevelStats>>

export interface Announcement {
  title?: string
  date?: string
  body?: string
}

export interface ResultDetail {
  n: number
  given: string
  ok: boolean
}

export interface TestResult {
  test_id: string
  title: string
  competition: string
  score: number
  total: number
  answered: number
  duration_s?: number
  details?: ResultDetail[]
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

export interface TaxonomyNode {
  en: string
  zh: string
  /** Depth in the taxonomy tree: 1 = domain, 2 = topic, 3 = tag. */
  level: number
}

/** Label map for the topic taxonomy; questions reference these ids. */
export interface Taxonomy {
  id: string
  version?: string
  name?: { en?: string; zh?: string }
  nodes: Record<string, TaxonomyNode>
}

/** One question as returned by the bank browser (`GET /api/questions`). */
export interface QuestionRow {
  /** Stable "slug:version:qid" key for React lists. */
  id: string
  qid: string
  /** Bank file stem, e.g. `amc12_A` or `amc12` for the v2 figure bank. */
  bank: string
  slug: string
  /** 1 = classic bank, 2 = figure bank. */
  version: number
  /** Display name from COMP_META, e.g. `AMC 12`. */
  competition: string
  set: string
  position: number | null
  source: string
  type: string
  points: number | null
  question: string
  question_zh: string
  choices: string[]
  answer: string
  solution: string
  solution_zh: string
  /** Topic id (taxonomy) the classifier picked, e.g. `algebra.substitution`. */
  primary: string | null
  /** Level-1 domain of `primary`. */
  domain: string | null
  /** All topic ids this question is tagged with (primary first, roughly). */
  tags: string[]
  /** Difficulty on the amc20 scale (20 = average AMC 12 #25); null when unclassified. */
  level: number | null
  band: string | null
  has_figure: boolean
  figure: { src?: string; alt?: string; width?: number; height?: number; kind?: string } | null
  has_solution: boolean
}

export interface QuestionFacets {
  all: number
  competition: Record<string, number>
  competition_labels: Record<string, string>
  domain: Record<string, number>
  level: Record<string, number>
  type: Record<string, number>
}

export interface QuestionPage {
  total: number
  limit: number
  offset: number
  counts: QuestionFacets
  items: QuestionRow[]
}

export interface QuestionQuery {
  q?: string
  comp?: string
  v?: string
  domain?: string
  topic?: string
  level_min?: string
  level_max?: string
  type?: string
  figure?: boolean
  classified?: boolean
  sort?: string
  limit?: number
  offset?: number
}

/** One row of reports.jsonl, as served by GET /api/reports. */
export interface ReportRow {
  id: string
  qid: string
  reason: string
  note?: string
  bank?: string
  version?: number
  source?: string
  competition?: string
  user?: string | null
  created_at?: string
  status?: string
}

/** Payload of POST /api/report; reason must be one of the server's REPORT_REASONS. */
export interface ReportBody {
  qid: string
  reason: string
  note?: string
  bank?: string
  version?: number
  source?: string
  competition?: string
  question?: string
}

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
  taxonomy: () => request<Taxonomy>('/api/taxonomy'),
  shsid: () =>
    request<{
      courses: {
        course_id: string
        course_title: string
        sections: {
          section_title: string
          activities: {
            modtype?: string
            title?: string
            restricted?: boolean
            files?: { path: string; name: string; ext: string; size: number }[]
          }[]
        }[]
      }[]
    }>('/api/shsid'),
  /** Bank browser: search + filter over every question on disk (paged). */
  questions: (query: QuestionQuery = {}) => {
    const params = new URLSearchParams()
    const put = (key: string, value: string | number | boolean | undefined) => {
      if (value === undefined || value === '') return
      params.set(key, String(value))
    }
    put('q', query.q)
    put('comp', query.comp)
    put('v', query.v)
    put('domain', query.domain)
    put('topic', query.topic)
    put('level_min', query.level_min)
    put('level_max', query.level_max)
    put('type', query.type)
    put('figure', query.figure ? 1 : '')
    put('classified', query.classified ? 1 : '')
    put('sort', query.sort)
    put('limit', query.limit)
    put('offset', query.offset)
    const qs = params.toString()
    return request<QuestionPage>(`/api/questions${qs ? `?${qs}` : ''}`)
  },
  tests: () => request<TestSummary[]>('/api/tests'),
  test: (id: string) => request<unknown>(`/api/test/${id}`),
  generate: (slug: string, round?: string | null, version?: 1 | 2) =>
    request<{ ok: boolean; id: string; bank_version?: number; fallback?: boolean }>(
      `/api/generate/${slug}${round ? `/${encodeURIComponent(round)}` : ''}${version === 2 ? '?v=2' : ''}`,
    ),
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
    details?: ResultDetail[]
  }) => post<{ ok: boolean; guest?: boolean }>('/api/result', payload),

  // question classification (teacher-authored: knowledge point, difficulty, key note)
  classify: (testId: string) => request<{ items: Record<string, { kp?: string; diff?: number; note?: string }> }>(
    `/api/test/${testId}/classify`,
  ),
  classifySave: (testId: string, items: Record<string, { kp?: string; diff?: number; note?: string }>) =>
    post<{ ok: boolean }>(`/api/test/${testId}/classify`, { items }),

  // build a practice test from the same banks at the positions you got wrong
  practiceSimilar: (items: { test_id: string; n: number }[]) =>
    post<{ ok: boolean; id: string }>('/api/practice_similar', { items }),
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

  // worksheets (upload a txt/md/json file -> printable worksheet)
  worksheetGenerate: (body: { filename: string; data_b64: string }) =>
    post<Worksheet>('/api/worksheet/generate', body),
  worksheet: (id: string) => request<Worksheet>(`/api/worksheet/${id}`),
  worksheets: () => request<WorksheetSummary[]>('/api/worksheets'),

  // practice drills
  practice: () => request<PracticeStats | { guest: true }>('/api/practice'),
  practiceSave: (body: { drill: string; level: string; pct: number; time_s: number; correct: number; total: number }) =>
    post<{ ok: boolean; stats: PracticeStats; new_best_pct: boolean; new_best_time: boolean }>(
      '/api/practice',
      body,
    ),

  // "report a problem" on a question (stored in reports.jsonl on the server)
  report: (body: ReportBody) => post<{ ok: boolean; id: string }>('/api/report', body),
  /** Reports the signed-in user filed, newest first. */
  reports: (limit = 50) => request<{ reports: ReportRow[]; count: number }>(`/api/reports?mine=1&limit=${limit}`),
}

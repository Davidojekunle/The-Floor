import { endSession, refreshSession } from '../auth/session'
import { tokenStorage } from '../auth/tokenStorage'
import { BASE_URL, CLIENT_HEADER } from './base'

/** Error codes the backend sends. See backend-truth.md for when each one happens. */
export type ErrorCode =
  | 'UNAUTHENTICATED'
  | 'INVALID_CREDENTIALS'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'ALREADY_MEMBER'
  | 'ALREADY_REQUESTED'
  | 'REQUEST_NOT_PENDING'
  | 'MEMBER_NOT_ACTIVE'
  | 'INVALID_TRANSITION'
  | 'LATER_STAGES_STARTED'
  | 'LAST_STAGE'
  | 'TASK_NOT_APPROVED'
  | 'ALREADY_APPROVED'
  | 'ALREADY_HEAD'
  | 'HEAD_MUST_TRANSFER'
  | 'RESET_TOKEN_INVALID'
  | 'EMAIL_TOKEN_INVALID'
  | 'RATE_LIMITED'
  | 'VALIDATION_ERROR'
  | 'METHOD_NOT_ALLOWED'
  | 'SERVER_ERROR'
  | 'SERVER_BUSY' // 503: every database connection was busy; worth retrying in a few seconds
  | 'NETWORK_ERROR'

export class ApiError extends Error {
  status: number
  code: ErrorCode | (string & {})
  fields?: Record<string, string>
  retryAfter?: number // seconds, on 429 RATE_LIMITED

  constructor(status: number, code: string, message: string, fields?: Record<string, string>, retryAfter?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields
    this.retryAfter = retryAfter
  }
}

export const API_BASE = BASE_URL

const NETWORK_MESSAGE = "Can't reach The Floor. Check your connection and try again."

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | undefined>
  auth?: boolean // false for register and login (no bearer token, and a 401 there never refreshes)
  session?: boolean // login, logout, logout-all: send the refresh cookie and the X-Taskroom-Client header
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, auth = true, session = false } = options

  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) params.set(key, String(value))
  }
  const url = BASE_URL + path + (params.size ? `?${params}` : '')

  const send = async () => {
    const headers: Record<string, string> = session ? { ...CLIENT_HEADER } : {}
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    const token = auth ? tokenStorage.get() : null
    if (token) headers['Authorization'] = `Bearer ${token}`
    try {
      return await fetch(url, {
        method,
        headers,
        credentials: session ? 'include' : 'same-origin',
        body: body !== undefined ? JSON.stringify(body) : undefined,
      })
    } catch {
      throw new ApiError(0, 'NETWORK_ERROR', NETWORK_MESSAGE)
    }
  }

  let response = await send()

  // The access token expired (or another tab's refresh replaced it): refresh once and try again.
  // Safe for writes too: the server checks the token before running any route code, so a 401 changed nothing.
  // The sign-in form's wrong password is INVALID_CREDENTIALS on an auth: false call, so it never gets here.
  // Only an expired or replaced token means "refresh". A wrong current password on change-password or
  // change-email is also a 401 (INVALID_CREDENTIALS), and must stay a form error, never a sign-out.
  const expired = response.status === 401 && auth && (await errorCode(response)) !== 'INVALID_CREDENTIALS'
  if (expired) {
    const refreshed = await refreshSession()
    if (refreshed.ok) response = await send()
    else if (refreshed.reason === 'unreachable') throw new ApiError(0, 'NETWORK_ERROR', NETWORK_MESSAGE)
  }

  if (response.status === 204) return undefined as T

  let data: unknown = null
  try {
    data = await response.json()
  } catch {
    // response had no JSON body
  }

  if (!response.ok) {
    const err = (data as { error?: { code?: string; message?: string; fields?: Record<string, string> } } | null)?.error
    const code = err?.code ?? 'SERVER_ERROR'
    if (response.status === 401 && auth && code !== 'INVALID_CREDENTIALS') endSession() // the refresh failed too: the session is over
    if (code === 'RATE_LIMITED') {
      const wait = Number(response.headers.get('Retry-After')) || 30
      throw new ApiError(429, code, `Too many attempts. Try again in ${waitLabel(wait)}.`, undefined, wait)
    }
    throw new ApiError(response.status, code, err?.message ?? 'Something went wrong.', err?.fields)
  }

  return data as T
}

/** "40 seconds", "2 minutes" */
export function waitLabel(seconds: number): string {
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} seconds`
  const m = Math.ceil(seconds / 60)
  return m === 1 ? 'a minute' : `${m} minutes`
}

/** The error code in a response, read from a copy so the body can still be read afterwards. */
async function errorCode(response: Response): Promise<string | undefined> {
  try {
    return ((await response.clone().json()) as { error?: { code?: string } })?.error?.code
  } catch {
    return undefined
  }
}

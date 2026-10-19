import { tokenStorage } from '../auth/tokenStorage'

// Relative by default: the Vite dev server proxies /api to the backend (see vite.config.ts),
// so the refresh cookie is same-origin.
const BASE_URL: string = import.meta.env.VITE_API_URL ?? '/api/v1'

// The backend refuses sign-in, refresh and logout without this header (it blocks cross-site requests).
const CLIENT_HEADER = { 'X-Taskroom-Client': 'web' }

export class ApiError extends Error {
  status: number
  code: string
  fields?: Record<string, string>

  constructor(
    status: number,
    code: string,
    message: string,
    fields?: Record<string, string>,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields
  }
}

// AuthProvider will register a function here that sends the user to login.
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

// Access tokens last 15 minutes. The backend keeps a 30-day refresh cookie; on a 401 we trade it for a
// new token once and retry. Concurrent 401s share one refresh call.
let refreshing: Promise<boolean> | null = null

export function refreshSession(): Promise<boolean> {
  refreshing ??= fetch(new URL(BASE_URL + '/auth/refresh', window.location.origin), {
    method: 'POST',
    headers: CLIENT_HEADER,
    credentials: 'include',
  })
    .then(async (response) => {
      if (!response.ok) return false
      const data = (await response.json()) as { access_token: string }
      tokenStorage.set(data.access_token)
      return true
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | undefined>
  auth?: boolean // false for register and login
  retried?: boolean // internal: already refreshed once
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = 'GET', body, query, auth = true, retried = false } = options

  const url = new URL(BASE_URL + path, window.location.origin)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
  }

  const headers: Record<string, string> = { ...CLIENT_HEADER }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth) {
    const token = tokenStorage.get()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers,
      credentials: 'include', // sends and receives the refresh cookie
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', 'Could not reach the server.')
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

    if (response.status === 401 && auth) {
      if (!retried && (await refreshSession())) {
        return apiRequest<T>(path, { ...options, retried: true })
      }
      tokenStorage.clear()
      onUnauthorized?.()
    }

    throw new ApiError(
      response.status,
      err?.code ?? 'SERVER_ERROR',
      err?.message ?? 'Something went wrong.',
      err?.fields,
    )
  }

  return data as T
}
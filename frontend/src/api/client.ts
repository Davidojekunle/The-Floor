import { tokenStorage } from '../auth/tokenStorage'

const BASE_URL: string =
  import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'

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

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | undefined>
  auth?: boolean // false for register and login
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = 'GET', body, query, auth = true } = options

  const url = new URL(BASE_URL + path)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
  }

  const headers: Record<string, string> = {}
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
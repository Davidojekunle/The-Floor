import type { Me } from '../api/auth'
import { BASE_URL, CLIENT_HEADER } from '../api/base'
import { tokenStorage } from './tokenStorage'

/*
 * Refresh tokens. The refresh cookie is shared by every tab, so refreshing is coordinated:
 * - One refresh at a time in this tab: concurrent callers share the same promise.
 * - One at a time across tabs: a Web Lock. A tab that waited checks whether another tab already got a fresh
 *   token (shared over a BroadcastChannel) and uses that instead of rotating the cookie again.
 * - A minute before expiry the token is refreshed in the background; a 401 from the API also triggers one.
 * Only a 401 from /auth/refresh ends the session. Being offline or a server error never logs anyone out.
 */

export type RefreshOutcome =
  | { ok: true; me: Me | null } // me is null when another tab refreshed for us
  | { ok: false; reason: 'ended' | 'unreachable' }

type Broadcast = { type: 'token'; token: string; expiresAt: number } | { type: 'ended' }

const LOCK = 'taskroom-refresh'
const EARLY_MS = 60_000 // refresh this long before the token expires
const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('taskroom-auth') : null

// ---- session end (registered by the auth provider)

let onSessionEnded: (() => void) | null = null

export function setSessionEndedHandler(handler: (() => void) | null): void {
  onSessionEnded = handler
}

/** The session is over: drop the token and send the user to sign in. */
export function endSession(): void {
  tokenStorage.clear()
  onSessionEnded?.()
}

/** Tell other tabs we signed out, so they don't keep showing a session whose cookie is gone. */
export function announceSignOut(): void {
  channel?.postMessage({ type: 'ended' } satisfies Broadcast)
}

// ---- refreshing

let inflight: Promise<RefreshOutcome> | null = null

export function refreshSession(): Promise<RefreshOutcome> {
  inflight ??= coordinated().finally(() => {
    inflight = null
  })
  return inflight
}

function coordinated(): Promise<RefreshOutcome> {
  const seen = tokenStorage.version()
  const work = async (): Promise<RefreshOutcome> => {
    // While we waited for the lock, another tab may have refreshed and shared its token.
    if (tokenStorage.version() !== seen && tokenStorage.expiresAt() - Date.now() > EARLY_MS) return { ok: true, me: null }
    return callRefresh()
  }
  return typeof navigator !== 'undefined' && navigator.locks ? navigator.locks.request(LOCK, work) : work()
}

async function callRefresh(): Promise<RefreshOutcome> {
  let res: Response
  try {
    res = await fetch(`${BASE_URL}/auth/refresh`, { method: 'POST', credentials: 'include', headers: CLIENT_HEADER })
    // Rate limited is temporary (a busy shared network): wait as told, then try again, twice at most.
    for (let i = 0; i < 2 && res.status === 429; i++) {
      const wait = Math.min(30, Number(res.headers.get('Retry-After')) || 5)
      await new Promise((r) => setTimeout(r, wait * 1000))
      res = await fetch(`${BASE_URL}/auth/refresh`, { method: 'POST', credentials: 'include', headers: CLIENT_HEADER })
    }
  } catch {
    return { ok: false, reason: 'unreachable' }
  }
  if (res.status === 401) {
    // The cookie is shared, so the session is over in every tab.
    tokenStorage.clear()
    announceSignOut()
    return { ok: false, reason: 'ended' }
  }
  if (!res.ok) return { ok: false, reason: 'unreachable' } // 5xx, or a 403 that means a bug on our side: don't log out
  const data = (await res.json()) as { access_token: string; expires_in: number; me: Me }
  acceptToken(data.access_token, data.expires_in)
  return { ok: true, me: data.me }
}

/** Store a token from login or refresh and share it with the other tabs. */
export function acceptToken(token: string, expiresInSeconds: number): void {
  const expiresAt = Date.now() + expiresInSeconds * 1000
  tokenStorage.set(token, expiresAt)
  channel?.postMessage({ type: 'token', token, expiresAt } satisfies Broadcast)
}

channel?.addEventListener('message', (e: MessageEvent<Broadcast>) => {
  const msg = e.data
  if (msg.type === 'token') {
    // Only tabs that are signed in take it: a tab on the sign-in page stays there.
    if (tokenStorage.get() !== null && msg.expiresAt > tokenStorage.expiresAt()) tokenStorage.set(msg.token, msg.expiresAt)
  } else if (msg.type === 'ended' && tokenStorage.get() !== null) {
    endSession()
  }
})

// ---- refresh a minute early, so requests rarely meet a 401

let timer: ReturnType<typeof setTimeout> | undefined
tokenStorage.subscribe((token) => {
  clearTimeout(timer)
  if (!token) return
  const wait = Math.max(5_000, tokenStorage.expiresAt() - Date.now() - EARLY_MS)
  timer = setTimeout(() => {
    void refreshSession().then((r) => {
      if (!r.ok && r.reason === 'ended') endSession()
      // unreachable: try again when the next request meets a 401
    })
  }, wait)
})

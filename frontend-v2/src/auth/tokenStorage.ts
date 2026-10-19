/*
 * The access token lives in memory only (it lasts 15 minutes). What keeps you signed in is the httpOnly
 * refresh cookie, which JavaScript can't read: on page load and before expiry, auth/session.ts trades it
 * for a new access token.
 */

let token: string | null = null
let expiresAt = 0 // ms since epoch
let version = 0
const listeners = new Set<(token: string | null) => void>()

// Tokens used to be kept in localStorage. Remove the leftover once.
try {
  localStorage.removeItem('the-floor-token')
} catch {
  // storage unavailable, nothing to clean
}

function emit() {
  version++
  for (const fn of listeners) fn(token)
}

export const tokenStorage = {
  get(): string | null {
    return token
  },

  /** `expiresAt` in ms since epoch. */
  set(next: string, expiresAtMs: number): void {
    token = next
    expiresAt = expiresAtMs
    emit()
  },

  clear(): void {
    if (token === null) return
    token = null
    expiresAt = 0
    emit()
  },

  expiresAt: () => expiresAt,

  /** Changes on every set/clear, so a waiting refresh can tell another tab already did the work. */
  version: () => version,

  /** Called with the new token (or null) whenever it changes. */
  subscribe(fn: (token: string | null) => void): () => void {
    listeners.add(fn)
    return () => void listeners.delete(fn)
  },
}

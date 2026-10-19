/** Where the API lives. Unset in development: /api/v1 is proxied by Vite, so the app and API share an origin. */
export const BASE_URL: string = import.meta.env?.VITE_API_URL ?? '/api/v1'

/** Sent on login, refresh, logout and logout-all. The server rejects them without it (blocks cross-site use of the cookie). */
export const CLIENT_HEADER = { 'X-Taskroom-Client': 'web' } as const

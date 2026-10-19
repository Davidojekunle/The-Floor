/*
 * The phase 7 socket: one per signed-in tab. It carries hints ("task T in room R changed"), never data,
 * so every event is answered by refetching through REST. Best effort: nothing is replayed, so after each
 * reconnect the app refetches what's on screen.
 *
 * Protocol: connect → send {"type":"auth","token"} → server replies {"type":"ready","rooms":[…]} → events.
 * The server sends protocol-level pings, which browsers answer themselves, so the client sends none.
 * Close code 4401: the token is bad or expired. The owner refreshes and we reconnect; only a failed refresh
 * ends the session. After each refresh, `reauth` sends the new token on the open socket ({"type":"auth"} →
 * {"type":"reauthed"}), which moves its expiry with no reconnect (and so no refetch of every screen).
 */

export type LiveEventType =
  | 'message_created'
  | 'message_deleted'
  | 'task_changed'
  | 'task_deleted'
  | 'task_updates_changed'
  | 'room_changed'
  | 'room_access_lost'
  | 'room_access_granted'
  | 'join_request_rejected'

export type LiveEvent = {
  type: LiveEventType | (string & {})
  room_id: string | null // null for events addressed to you, not a room (account_changed, notifications)
  at: string
  task_id?: string
  stage_id?: string
  message_id?: string
  reason?: string // room_access_lost: removed | left | room_deleted
  notification_id?: string // notification_created
  user_id?: string // typing: who
  typing?: boolean // typing: started (true) or stopped (false)
}

export type LiveStatus = 'connecting' | 'live' | 'down'

type Handlers = {
  onReady: (rooms: string[], reconnected: boolean) => void
  onEvent: (event: LiveEvent) => void
  onStatus: (status: LiveStatus) => void
  /** 4401 or no token. Resolve true to reconnect (refreshed), false to stay closed (the session is over). */
  onUnauthorized: () => Promise<boolean>
}

const MAX_BACKOFF_MS = 30_000

export class LiveSocket {
  private ws: WebSocket | null = null
  private stopped = false
  private failures = 0
  private everReady = false
  private ready = false
  private rejected = 0 // 4401s in a row; a refresh that doesn't help shouldn't loop
  private retryTimer: ReturnType<typeof setTimeout> | undefined
  private readonly url: string
  private readonly getToken: () => string | null
  private readonly on: Handlers

  constructor(url: string, getToken: () => string | null, handlers: Handlers) {
    this.url = url
    this.getToken = getToken
    this.on = handlers
  }

  start() {
    this.stopped = false
    globalThis.addEventListener?.('online', this.retryNow)
    this.connect()
  }

  stop() {
    this.stopped = true
    clearTimeout(this.retryTimer)
    globalThis.removeEventListener?.('online', this.retryNow)
    const ws = this.ws
    this.ws = null
    ws?.close(1000)
  }

  /** Send a refreshed token on the open socket so the server moves its expiry. */
  reauth(token: string) {
    if (this.ready && this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: 'auth', token }))
  }

  /** Fire-and-forget (typing). Dropped while not connected: nothing here needs to be delivered late. */
  send(payload: Record<string, unknown>) {
    if (this.ready && this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(payload))
  }

  /** Back online: don't sit out the rest of a long backoff. */
  private retryNow = () => {
    if (this.stopped || this.ws) return
    clearTimeout(this.retryTimer)
    this.connect()
  }

  private connect() {
    const token = this.getToken()
    if (!token) return this.unauthorized()
    this.on.onStatus('connecting')

    let ws: WebSocket
    try {
      ws = new WebSocket(this.url)
    } catch {
      return this.scheduleRetry()
    }
    this.ws = ws

    ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token }))

    ws.onmessage = (msg) => {
      let data: { type?: string; rooms?: string[]; room_id?: string | null }
      try {
        data = JSON.parse(String(msg.data))
      } catch {
        return
      }
      if (data.type === 'ready') {
        this.failures = 0
        this.rejected = 0
        this.ready = true
        this.on.onStatus('live')
        this.on.onReady(data.rooms ?? [], this.everReady)
        this.everReady = true
      } else if (data.type && data.type !== 'pong' && data.type !== 'reauthed' && 'room_id' in data) {
        this.on.onEvent(data as LiveEvent)
      }
    }

    ws.onclose = (e) => {
      if (this.ws !== ws) return // replaced or stopped on purpose
      this.ws = null
      this.ready = false
      if (this.stopped) return
      if (e.code === 4401) return this.unauthorized()
      if (e.code === 4429) this.failures = Math.max(this.failures, 5) // rate limited: wait ~30s, not 1s
      this.scheduleRetry()
    }
  }

  private async unauthorized() {
    this.on.onStatus('down')
    if (++this.rejected > 2) return // refreshed twice and still rejected: leave it to REST to notice
    const again = await this.on.onUnauthorized()
    if (this.stopped) return
    if (again) this.connect()
    else this.stopped = true
  }

  private scheduleRetry() {
    this.on.onStatus('down')
    // 1s, 2s, 4s … up to 30s, with a little jitter so many tabs don't reconnect in lockstep after a restart.
    const base = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.failures++)
    this.retryTimer = setTimeout(() => this.connect(), base * (0.8 + Math.random() * 0.4))
  }
}

/** ws(s)://<api base>/ws, worked out from the REST base so it follows VITE_API_URL and the dev proxy. */
export function liveUrl(restBase: string): string {
  const u = new URL(`${restBase.replace(/\/$/, '')}/ws`, globalThis.location?.href)
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
  return u.toString()
}

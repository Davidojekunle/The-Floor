import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { API_BASE } from '../api/client'
import { endSession, refreshSession } from '../auth/session'
import { useAuth } from '../auth/useAuth'
import { tokenStorage } from '../auth/tokenStorage'
import { useToast } from '../components/toastContext'
import { lastRoom } from '../lib/lastRoom'
import { roomExits, type ExitReason } from '../room/roomExits'
import { LiveContext, type LiveSignal } from './liveContext'
import { LiveSocket, liveUrl, type LiveEvent } from './liveSocket'

const ME_THROTTLE_MS = 2500 // badges: at most one /me refetch per 2.5s, however many events arrive
const ME_POLL_MS = 30_000 // while the socket is down (the phase 6 behaviour)
const ME_SAFETY_MS = 5 * 60_000 // while it's up: events do the work, this only covers a missed one

/**
 * Live updates (phase 7). Each event names what changed, and we refetch it through REST by invalidating
 * the matching queries (only the ones on screen actually refetch). Chat listens through useLiveSignals.
 * Also owns the /me refresh that keeps badges (unread, waiting on you) current.
 */
export function LiveProvider({ children }: { children: ReactNode }) {
  const { user, refreshUser } = useAuth()
  const queryClient = useQueryClient()
  const toast = useToast()
  const [live, setLive] = useState(false)
  const listeners = useRef(new Set<(s: LiveSignal) => void>())
  const signedIn = user?.id ?? null

  // Room names for toasts, as they were before an event changed /me.
  const roomNames = useRef(new Map<string, string>())
  useEffect(() => {
    for (const r of user?.rooms ?? []) roomNames.current.set(r.id, r.name)
  }, [user])

  // ---- /me: throttled after events, polled as a fallback
  const lastMe = useRef(0)
  const meTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const meSoon = useCallback(() => {
    if (meTimer.current) return // one is already queued
    const wait = Math.max(0, lastMe.current + ME_THROTTLE_MS - Date.now())
    meTimer.current = setTimeout(() => {
      meTimer.current = undefined
      lastMe.current = Date.now()
      refreshUser().catch(() => {})
    }, wait)
  }, [refreshUser])

  useEffect(() => {
    if (!signedIn) return
    const tick = () => document.visibilityState === 'visible' && meSoon()
    const id = window.setInterval(tick, live ? ME_SAFETY_MS : ME_POLL_MS)
    document.addEventListener('visibilitychange', tick)
    return () => {
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [signedIn, live, meSoon])

  useEffect(() => () => clearTimeout(meTimer.current), [])

  // ---- events → caches
  const handle = useCallback(
    (e: LiveEvent) => {
      const r = e.room_id ?? '' // room events always carry one; null only on events addressed to you
      const inv = (queryKey: unknown[]) => void queryClient.invalidateQueries({ queryKey })
      switch (e.type) {
        case 'message_created':
        case 'message_deleted':
          inv(['activity', r]) // Home's "Recent activity"
          meSoon() // unread counts; an open chat fetches the message itself
          break
        case 'task_changed':
        case 'task_deleted': // the task page refetches, gets 404 and says the task is gone
          inv(['task', r, e.task_id])
          inv(['tasks', r])
          inv(['me-tasks'])
          meSoon()
          break
        case 'task_updates_changed':
          inv(['updates', r, e.task_id])
          inv(['task', r, e.task_id]) // update_count
          break
        case 'room_changed': // permissions, tags, members, requests, temp-head grants and expiry
          for (const key of ['room', 'members', 'tags', 'join-requests', 'tasks']) inv([key, r])
          inv(['me-tasks'])
          meSoon()
          break
        case 'room_access_lost': {
          const known = roomNames.current.get(r)
          const name = known ?? 'A room'
          const reason = (e.reason ?? 'removed') as ExitReason
          const own = roomExits.isOwn(r) // this tab did it and already said so
          roomExits.note(r, reason, known)
          lastRoom.forget(r)
          inv(['room', r]) // an open room refetches, gets 404 and shows why (see RoomProvider)
          inv(['me-tasks'])
          refreshUser().catch(() => {})
          if (!own)
            toast(
              reason === 'room_deleted'
                ? `${name} was deleted.`
                : reason === 'left'
                  ? `You left ${name}.`
                  : `You were removed from ${name}.`,
            )
          break
        }
        case 'room_access_granted':
          inv(['join-preview'])
          inv(['me-tasks'])
          refreshUser().then(
            (me) => {
              const room = me.rooms.find((x) => x.id === r)
              toast(room ? `You're in ${room.name}. It's in your rooms now.` : 'Your request to join was approved.')
            },
            () => {},
          )
          break
        case 'notification_created': // a new bell item: refresh the list and the badge right away
          inv(['notifications'])
          refreshUser().catch(() => {})
          break
        case 'account_changed': // name, timezone, theme, email or pending email changed (here or elsewhere)
          refreshUser().catch(() => {})
          break
        case 'join_request_rejected':
          inv(['join-preview'])
          toast("Your request to join a room wasn't approved.")
          break
      }
      for (const fn of listeners.current) fn(e)
    },
    [queryClient, meSoon, refreshUser, toast],
  )

  const handleRef = useRef(handle)
  useEffect(() => {
    handleRef.current = handle
  })

  // ---- the socket: open while signed in
  useEffect(() => {
    if (!signedIn) return
    const socket = new LiveSocket(liveUrl(API_BASE), tokenStorage.get, {
      onStatus: (s) => setLive(s === 'live'),
      onEvent: (e) => handleRef.current(e),
      onReady: (_rooms, reconnected) => {
        // Events were missed while we were away: refetch everything on screen, and let chat catch up.
        if (reconnected) {
          void queryClient.invalidateQueries()
          lastMe.current = 0
        }
        for (const fn of listeners.current) fn({ type: 'ready' })
      },
      onUnauthorized: async () => {
        const r = await refreshSession()
        if (r.ok) return true
        if (r.reason === 'ended') endSession()
        return false // unreachable: REST requests will notice and retry the refresh
      },
    })
    socket.start()
    // Each refresh (here or in another tab) re-authenticates the open socket instead of reconnecting it.
    const unsubscribe = tokenStorage.subscribe((token) => token && socket.reauth(token))
    return () => {
      unsubscribe()
      socket.stop()
      setLive(false)
    }
  }, [signedIn, queryClient])

  const subscribe = useCallback((fn: (s: LiveSignal) => void) => {
    listeners.current.add(fn)
    return () => void listeners.current.delete(fn)
  }, [])

  const value = useMemo(() => ({ live, subscribe }), [live, subscribe])
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>
}

import { createContext, useContext, useEffect, useRef } from 'react'
import type { LiveEvent } from './liveSocket'

/** What subscribers hear: socket events, plus 'ready' after every (re)connect (refetch what you show). */
export type LiveSignal = LiveEvent | { type: 'ready' }

export type LiveContextValue = {
  /** The socket is connected and authenticated. While false, screens keep polling as before. */
  live: boolean
  subscribe: (listener: (signal: LiveSignal) => void) => () => void
}

export const LiveContext = createContext<LiveContextValue>({ live: false, subscribe: () => () => {} })

export const useLive = () => useContext(LiveContext)

/** Run `handler` for each live signal. The latest handler is always used, so it needn't be memoised. */
export function useLiveSignals(handler: (signal: LiveSignal) => void) {
  const { subscribe } = useLive()
  const latest = useRef(handler)
  useEffect(() => {
    latest.current = handler
  })
  useEffect(() => subscribe((s) => latest.current(s)), [subscribe])
}

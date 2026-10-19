import { useCallback, useEffect, useRef, useState } from 'react'
import { useLive, useLiveSignals } from '../live/liveContext'

const SEND_EVERY_MS = 3000 // while typing, remind the room this often
const IDLE_MS = 5000 // no keystrokes for this long counts as stopped
const FORGET_MS = 6000 // someone else's "typing" fades if no reminder arrives (closed tab, lost signal)

/**
 * "Femi is typing…" for one room's chat. Signals go over the live socket and are never stored.
 * `typed(text)` on every change of the draft; `stopped()` when the message is sent.
 */
export function useTyping(roomId: string, myId: string | undefined) {
  const { sendTyping } = useLive()
  const [typers, setTypers] = useState<Map<string, number>>(() => new Map()) // user id -> forget at
  const active = useRef(false)
  const lastSent = useRef(0)
  const idle = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useLiveSignals((s) => {
    if (s.type === 'ready') return setTypers(new Map()) // reconnected: start clean
    if (s.type !== 'typing' || !('room_id' in s) || s.room_id !== roomId || !s.user_id || s.user_id === myId) return
    const who = s.user_id
    setTypers((prev) => {
      const next = new Map(prev)
      if (s.typing === false) next.delete(who)
      else next.set(who, Date.now() + FORGET_MS)
      return next
    })
  })

  // Fade out anyone whose reminders stopped.
  const anyone = typers.size > 0
  useEffect(() => {
    if (!anyone) return
    const t = setInterval(() => {
      const now = Date.now()
      setTypers((prev) => {
        const next = new Map([...prev].filter(([, until]) => until > now))
        return next.size === prev.size ? prev : next
      })
    }, 1000)
    return () => clearInterval(t)
  }, [anyone])

  const stopped = useCallback(() => {
    clearTimeout(idle.current)
    if (!active.current) return
    active.current = false
    lastSent.current = 0
    sendTyping(roomId, false)
  }, [roomId, sendTyping])

  const typed = useCallback(
    (text: string) => {
      if (!text.trim()) return stopped()
      const now = Date.now()
      if (!active.current || now - lastSent.current > SEND_EVERY_MS) {
        active.current = true
        lastSent.current = now
        sendTyping(roomId, true)
      }
      clearTimeout(idle.current)
      idle.current = setTimeout(stopped, IDLE_MS)
    },
    [roomId, sendTyping, stopped],
  )

  useEffect(() => stopped, [stopped]) // leaving the chat stops it

  return { typers: [...typers.keys()], typed, stopped }
}

/** "Femi is typing", "Femi and Tola are typing", "Several people are typing". */
export function typingLabel(names: string[]): string {
  if (names.length === 0) return ''
  if (names.length === 1) return `${names[0]} is typing`
  if (names.length === 2) return `${names[0]} and ${names[1]} are typing`
  return 'Several people are typing'
}

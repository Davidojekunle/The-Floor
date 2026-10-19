import { useSyncExternalStore } from 'react'

/*
 * Why a room went away, so every screen can say so: removed by the head, left (in another tab), or deleted.
 * Filled from the live `room_access_lost` event (its `reason`). Rooms this tab left or deleted itself are
 * marked too, so the event that echoes back doesn't announce what the person just did.
 * Observable: an open room switches to "this room was deleted" the moment the event arrives.
 */
export type ExitReason = 'removed' | 'left' | 'room_deleted'
type Exit = { reason: ExitReason; name?: string; at: number } // at: when we learned of it

const exits = new Map<string, Exit>()
const ownExits = new Set<string>()
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((fn) => fn())

export const roomExits = {
  note(roomId: string, reason: ExitReason, name?: string) {
    exits.set(roomId, { reason, name: name ?? exits.get(roomId)?.name, at: Date.now() })
    emit()
  },
  get(roomId: string): Exit | undefined {
    return exits.get(roomId)
  },
  markOwn(roomId: string, reason: ExitReason, name: string) {
    ownExits.add(roomId)
    exits.set(roomId, { reason, name, at: Date.now() })
    emit()
  },
  isOwn(roomId: string): boolean {
    return ownExits.has(roomId)
  },
}

/** The latest exit recorded for this room, re-rendering when one arrives. */
export function useRoomExit(roomId: string): Exit | undefined {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => void listeners.delete(fn)
    },
    () => exits.get(roomId),
  )
}

import { createContext, useContext } from 'react'
import type { Room } from '../api/rooms'

export type RoomContextValue = {
  room: Room
  refreshRoom: () => void
}

export const RoomContext = createContext<RoomContextValue | null>(null)

export function useRoom() {
  const ctx = useContext(RoomContext)
  if (!ctx) throw new Error('useRoom must be used inside <RoomProvider>')
  return ctx
}

/** Gate UI on the room's permissions list. Never branch on my_role for access. */
export function useCan(permission: string): boolean {
  return useRoom().room.permissions.includes(permission)
}

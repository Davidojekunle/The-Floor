import { createContext } from 'react'
import type { Room } from '../api/room'

export type RoomContextValue = {
  room: Room
  refreshRoom: () => void
}

export const RoomContext = createContext<RoomContextValue | null>(null)
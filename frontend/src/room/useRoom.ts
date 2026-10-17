import { useContext } from 'react'
import { RoomContext } from './roomContext'

export function useRoom() {
  const ctx = useContext(RoomContext)
  if (!ctx) throw new Error('useRoom must be used inside <RoomProvider>')
  return ctx
}

export function useCan(permission: string): boolean {
  return useRoom().room.permissions.includes(permission)
}
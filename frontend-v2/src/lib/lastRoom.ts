/** The room you were last in, so signing in (and the shell outside a room) can take you back to it. */
const KEY = 'floor-last-room'

export const lastRoom = {
  get(): string | null {
    try {
      return localStorage.getItem(KEY)
    } catch {
      return null
    }
  },
  /** Forget it if it's this room (you left it, or it was deleted). */
  forget(roomId: string): void {
    try {
      if (localStorage.getItem(KEY) === roomId) localStorage.removeItem(KEY)
    } catch {
      // nothing to forget
    }
  },
  set(roomId: string): void {
    try {
      localStorage.setItem(KEY, roomId)
    } catch {
      // storage unavailable: you'll land on the rooms list instead
    }
  },
}

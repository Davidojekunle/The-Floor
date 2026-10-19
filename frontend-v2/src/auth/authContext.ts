import { createContext } from 'react'
import type { Me, RegisterInput } from '../api/auth'

export type AuthContextValue = {
  user: Me | null
  /** True while the page-load refresh is running. */
  loading: boolean
  /** The page-load refresh couldn't reach the server (offline, or the API is down). Not the same as signed out. */
  unreachable: boolean
  retry: () => Promise<void>
  /** True after the server ended the session, so the sign-in page can explain why. */
  sessionExpired: boolean
  login: (email: string, password: string) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => Promise<void>
  /** Sign out on every device. Rejects if the server couldn't be reached. */
  logoutEverywhere: () => Promise<void>
  refreshUser: () => Promise<Me>
  /** Use a /me body the server just returned (e.g. from PATCH /me), without fetching again. */
  setMe: (me: Me) => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

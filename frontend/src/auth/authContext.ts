import { createContext } from 'react'
import type { Me, RegisterInput } from '../api/auth'

export type AuthContextValue = {
  user: Me | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
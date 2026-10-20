import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  getMe,
  loginRequest,
  registerRequest,
  type Me,
  type RegisterInput,
} from '../api/auth'
import { apiRequest, refreshSession, setUnauthorizedHandler } from '../api/client'
import { AuthContext } from './authContext'
import { tokenStorage } from './tokenStorage'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  // On page load, restore the session: from the saved token, or else from the refresh cookie.
  useEffect(() => {
    const restore = tokenStorage.get() ? Promise.resolve(true) : refreshSession()
    restore
      .then((ok) => (ok ? getMe().then(setUser) : undefined))
      .catch(() => tokenStorage.clear())
      .finally(() => setLoading(false))
  }, [])

  // When the API client sees a 401, drop the user so pages redirect to login.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(null)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const res = await loginRequest(email, password)
    tokenStorage.set(res.access_token)
    setUser(await getMe())
  }, [])

  const register = useCallback(
    async (input: RegisterInput) => {
      await registerRequest(input)
      await login(input.email, input.password)
    },
    [login],
  )

  const logout = useCallback(() => {
    // Ends the session on the server too, so the refresh cookie can't sign back in.
    apiRequest('/auth/logout', { method: 'POST', auth: false }).catch(() => {})
    tokenStorage.clear()
    setUser(null)
  }, [])

  const refreshUser = useCallback(async () => {
    setUser(await getMe())
  }, [])

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  )
}
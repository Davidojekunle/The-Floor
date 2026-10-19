import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getMe, loginRequest, logoutAllRequest, logoutRequest, registerRequest, type Me, type RegisterInput } from '../api/auth'
import { AuthContext } from './authContext'
import { applyTheme } from '../lib/theme'
import { sessionHint } from './sessionHint'
import { acceptToken, announceSignOut, refreshSession, setSessionEndedHandler, type RefreshOutcome } from './session'
import { tokenStorage } from './tokenStorage'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<Me | null>(null)
  const [sessionExpired, setSessionExpired] = useState(false)
  const [loading, setLoading] = useState(true)
  const [unreachable, setUnreachable] = useState(false)

  // On page load (and in every new tab), trade the refresh cookie for a token. The response includes /me.
  const apply = useCallback(async (r: RefreshOutcome) => {
    if (r.ok) {
      try {
        setUser(r.me ?? (await getMe()))
      } catch {
        setUnreachable(true)
      }
    } else if (r.reason === 'unreachable') {
      setUnreachable(true) // offline or the server is down: say so, don't send them to sign in
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    void refreshSession().then(apply)
  }, [apply])

  const retry = useCallback(async () => {
    setLoading(true)
    setUnreachable(false)
    await apply(await refreshSession())
  }, [apply])

  // The account's theme wins once we know it (it may have changed on another device).
  const theme = user?.theme
  useEffect(() => {
    if (theme) applyTheme(theme)
  }, [theme])

  // Remember whether there's a session, so "/" can skip the landing page flash for returning users.
  useEffect(() => {
    if (!loading) sessionHint.set(!!user)
  }, [user, loading])

  // When the session ends (a failed refresh here, or sign-out in another tab), drop the user and every cached room.
  useEffect(() => {
    setSessionEndedHandler(() => {
      queryClient.clear()
      setSessionExpired(true)
      setUser(null)
    })
    return () => setSessionEndedHandler(null)
  }, [queryClient])

  // Keeping /me fresh (badges, unread counts) is LiveProvider's job: on live events, or by polling as a fallback.

  const login = useCallback(async (email: string, password: string) => {
    const res = await loginRequest(email, password)
    acceptToken(res.access_token, res.expires_in)
    setSessionExpired(false)
    setUnreachable(false)
    setUser(await getMe())
  }, [])

  const register = useCallback(
    async (input: RegisterInput) => {
      await registerRequest(input)
      await login(input.email, input.password)
    },
    [login],
  )

  const signOutLocally = useCallback(() => {
    tokenStorage.clear()
    announceSignOut()
    queryClient.clear()
    setSessionExpired(false)
    setUser(null)
  }, [queryClient])

  const logout = useCallback(async () => {
    // Clear the cookie on the server first. If that fails (offline), sign out here anyway.
    await logoutRequest().catch(() => {})
    signOutLocally()
  }, [signOutLocally])

  const logoutEverywhere = useCallback(async () => {
    await logoutAllRequest() // a failure is shown by the caller; nothing changes locally
    signOutLocally()
  }, [signOutLocally])

  const refreshUser = useCallback(async () => {
    const me = await getMe()
    setUser(me)
    return me
  }, [])

  return (
    <AuthContext.Provider
      value={{ user, loading, unreachable, retry, sessionExpired, login, register, logout, logoutEverywhere, refreshUser, setMe: setUser }}
    >
      {children}
    </AuthContext.Provider>
  )
}

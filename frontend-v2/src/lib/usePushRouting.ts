import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { markNotificationRead } from '../api/notifications'
import { useAuth } from '../auth/useAuth'
import { resumePush } from './push'

/**
 * Inside the signed-in shell: keeps this device's push registration current, and handles taps on a pop-up
 * (the service worker either messages an open tab or opens one at the target with ?n=<notification id>).
 */
export function usePushRouting() {
  const { user, refreshUser } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const userId = user?.id

  useEffect(() => {
    if (userId) void resumePush(userId)
  }, [userId])

  useEffect(() => {
    const read = (id: unknown) => {
      if (typeof id !== 'string') return
      void markNotificationRead(id).then(
        () => {
          void queryClient.invalidateQueries({ queryKey: ['notifications'] })
          void refreshUser().catch(() => {})
        },
        () => {},
      )
    }
    // Opened by tapping a pop-up while no tab was open.
    const params = new URLSearchParams(location.search)
    if (params.has('n')) {
      read(params.get('n'))
      params.delete('n')
      const rest = params.toString()
      navigate({ pathname: location.pathname, search: rest ? `?${rest}` : '' }, { replace: true })
    }
    if (!('serviceWorker' in navigator)) return
    const onMessage = (e: MessageEvent) => {
      if (e.data?.type !== 'open-notification' || typeof e.data.url !== 'string' || !e.data.url.startsWith('/')) return
      navigate(e.data.url)
      read(e.data.id)
    }
    navigator.serviceWorker.addEventListener('message', onMessage)
    return () => navigator.serviceWorker.removeEventListener('message', onMessage)
  }, [location.pathname, location.search, navigate, queryClient, refreshUser])
}

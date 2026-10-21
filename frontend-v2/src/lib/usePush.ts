import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth/useAuth'
import { useToast } from '../components/toastContext'
import { disablePush, enablePush, pushReachedServer, pushState, type PushState } from './push'

/** This browser's push state, and the on/off action (which asks for permission the first time). */
export function usePush() {
  const { user } = useAuth()
  const toast = useToast()
  const [state, setState] = useState<PushState | null>(null)
  const [busy, setBusy] = useState(false)
  const [unsynced, setUnsynced] = useState(false) // on in this browser, but the server doesn't have it

  useEffect(() => {
    let alive = true
    void pushState().then(async (s) => {
      if (!alive) return
      setState(s)
      if (s === 'on' && !(await pushReachedServer()) && alive) setUnsynced(true)
    })
    return () => {
      alive = false
    }
  }, [])

  const set = useCallback(
    async (on: boolean) => {
      if (!user) return
      setBusy(true)
      try {
        const next = on ? await enablePush(user.id) : await disablePush(user.id)
        setState(next)
        setUnsynced(false)
        if (on && next === 'on') toast('Notifications are on for this device.')
        if (on && next === 'denied') toast('Notifications are blocked for this site in your browser settings.')
      } catch {
        toast(on ? "Couldn't turn on notifications here. Try again." : "Couldn't turn off notifications here. Try again.")
      } finally {
        setBusy(false)
      }
    },
    [user, toast],
  )

  return { state, busy, unsynced, set }
}

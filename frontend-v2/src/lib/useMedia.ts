import { useSyncExternalStore } from 'react'

/** Phone layout: bottom tab bar, sheets instead of popovers and dialogs. Matches the CSS breakpoint in shell.css. */
export const PHONE_QUERY = '(max-width: 760px)'

export function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia(query)
      mq.addEventListener('change', onChange)
      return () => mq.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}

export const useIsPhone = () => useMedia(PHONE_QUERY)

export const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

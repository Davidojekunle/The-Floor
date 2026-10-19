import { useAuth } from '../auth/useAuth'

/** The user's profile timezone, used for every date shown or picked. */
export function useTimezone(): string {
  const { user } = useAuth()
  return user?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone
}

/**
 * Whether this browser had a signed-in session last time. Lets "/" decide what to show before the
 * page-load refresh answers (about a second on a slow API): a likely-returning user waits for it and goes
 * to their room; a visitor sees the landing page at once instead of a blank screen. Only a hint: the
 * refresh still decides.
 */
const KEY = 'floor-had-session'

export const sessionHint = {
  get(): boolean {
    try {
      return localStorage.getItem(KEY) === '1'
    } catch {
      return false
    }
  },
  set(signedIn: boolean): void {
    try {
      if (signedIn) localStorage.setItem(KEY, '1')
      else localStorage.removeItem(KEY)
    } catch {
      // not remembered: the landing page may show for a moment, that's all
    }
  },
}

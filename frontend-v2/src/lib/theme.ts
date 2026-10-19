import type { Theme } from '../api/auth'

/*
 * Light / dark mode. "system" follows the device (and switches live with it, via the CSS media query).
 * The choice is saved on the account; it's also cached here so index.html can apply it before the first
 * paint (no flash of the wrong theme), then the account's value takes over once /me arrives.
 */
const KEY = 'floor-theme'

export function applyTheme(theme: Theme) {
  const root = document.documentElement
  if (theme === 'system') delete root.dataset.theme
  else root.dataset.theme = theme
  // Browser UI (address bar on phones) follows too.
  const dark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.querySelector('meta[name="theme-color"]:not([media])')?.setAttribute('content', dark ? '#121212' : '#f6f6f5')
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    // not cached: the account's theme still applies once signed in
  }
}

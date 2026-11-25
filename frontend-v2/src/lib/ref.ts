/**
 * Which link brought someone here: thefloorapp.me/?ref=linkedin. The word is kept in this browser (no cookie,
 * nothing sent anywhere) until they sign up, then saved on their account so the admin page can count sign-ups
 * and rooms by where they came from. The first link wins; it's forgotten after 60 days.
 */
const KEY = 'floor.ref'
const DAYS = 60

function clean(v: string | null): string | null {
  if (!v) return null
  const w = v.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '').slice(0, 32)
  return w || null
}

/** Call once on load. Also takes utm_source, and tidies the word out of the address bar. */
export function captureRef() {
  try {
    const url = new URL(window.location.href)
    const word = clean(url.searchParams.get('ref') ?? url.searchParams.get('utm_source'))
    if (!word) return
    if (!getRef()) localStorage.setItem(KEY, JSON.stringify({ ref: word, at: Date.now() }))
    url.searchParams.delete('ref')
    url.searchParams.delete('utm_source')
    window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash)
  } catch {
    // storage off or blocked: the sign-up just counts as "direct"
  }
}

export function getRef(): string | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const { ref, at } = JSON.parse(raw) as { ref: string; at: number }
    if (Date.now() - at > DAYS * 86_400_000) {
      localStorage.removeItem(KEY)
      return null
    }
    return clean(ref)
  } catch {
    return null
  }
}

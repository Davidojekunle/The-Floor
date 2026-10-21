/*
 * Browser push for this device. The service worker (public/sw.js) shows the pop-ups; this file turns them on
 * and off and keeps the server's copy of the subscription current.
 *
 * The choice is remembered per person on this browser ("floor-push:<user id>"), so signing out stops pushes
 * here, signing back in quietly resumes them, and someone else signing in on the same browser never inherits them.
 */
import { getPushConfig, removePushSubscription, savePushSubscription } from '../api/push'

export type PushState = 'unsupported' | 'needs-install' | 'denied' | 'off' | 'on'

const prefKey = (userId: string) => `floor-push:${userId}`

function remember(userId: string, on: boolean) {
  try {
    if (on) localStorage.setItem(prefKey(userId), 'on')
    else localStorage.removeItem(prefKey(userId))
  } catch {
    // private mode: push still works for this visit
  }
}

function wanted(userId: string) {
  try {
    return localStorage.getItem(prefKey(userId)) === 'on'
  } catch {
    return false
  }
}

export const pushSupported = () =>
  typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window

const isIos = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)

/** iPhone and iPad only offer push to sites added to the Home Screen. */
const needsInstall = () => isIos() && !pushSupported()

export function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return
  window.addEventListener('load', () => void navigator.serviceWorker.register('/sw.js').catch(() => {}))
}

async function currentSubscription(): Promise<PushSubscription | null> {
  const reg = await navigator.serviceWorker.getRegistration()
  return (await reg?.pushManager.getSubscription()) ?? null
}

export async function pushState(): Promise<PushState> {
  if (!pushSupported()) return needsInstall() ? 'needs-install' : 'unsupported'
  if (Notification.permission === 'denied') return 'denied'
  if (Notification.permission !== 'granted') return 'off'
  return (await currentSubscription()) ? 'on' : 'off'
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const b64 = (base64url + '='.repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(b64)
  const out = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

function sameKey(sub: PushSubscription, key: Uint8Array) {
  const had = sub.options.applicationServerKey
  if (!had) return false
  const a = new Uint8Array(had)
  return a.length === key.length && a.every((v, i) => v === key[i])
}

/** Subscribe (or reuse the subscription) and tell the server. Permission must already be granted. */
async function register(): Promise<void> {
  const reg = await navigator.serviceWorker.ready
  const key = keyBytes((await getPushConfig()).public_key)
  let sub = await reg.pushManager.getSubscription()
  if (sub && !sameKey(sub, key)) {
    await sub.unsubscribe() // made for another server key: start over
    sub = null
  }
  sub ??= await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key })
  await savePushSubscription(sub.toJSON())
}

/** From a tap on the switch: asks for permission (the browser shows its prompt). */
export async function enablePush(userId: string): Promise<PushState> {
  if (!pushSupported()) return needsInstall() ? 'needs-install' : 'unsupported'
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return permission === 'denied' ? 'denied' : 'off'
  await register()
  resumed = Promise.resolve(true)
  remember(userId, true)
  return 'on'
}

export async function disablePush(userId: string): Promise<PushState> {
  remember(userId, false)
  const sub = pushSupported() ? await currentSubscription() : null
  if (sub) {
    await removePushSubscription(sub.endpoint).catch(() => {})
    await sub.unsubscribe().catch(() => {})
  }
  return pushSupported() ? 'off' : 'unsupported'
}

// Whether this start's re-registration reached the server. The browser can hold a subscription the server
// never got (it was down or busy), and then nothing arrives even though the switch says on.
let resumed: Promise<boolean> | null = null

/** After sign-in and on each start: if this person turned push on here, make sure the server still has it. */
export async function resumePush(userId: string): Promise<void> {
  if (!pushSupported() || Notification.permission !== 'granted' || !wanted(userId)) return
  resumed = register().then(
    () => true,
    () => false,
  )
  await resumed
}

/** False when this start's re-registration failed. Turning the switch on again retries. */
export const pushReachedServer = (): Promise<boolean> => resumed ?? Promise.resolve(true)

/**
 * Signing out: this browser stops getting pushes for the account. With a live session the server forgets it now;
 * otherwise (expired session) the browser's subscription is dropped and the server cleans up on the next push.
 * The person's choice is kept, so signing back in resumes it.
 */
export async function pausePush(opts: { tellServer: boolean }): Promise<void> {
  if (!pushSupported()) return
  const sub = await currentSubscription().catch(() => null)
  if (!sub) return
  if (opts.tellServer) {
    await Promise.race([removePushSubscription(sub.endpoint).catch(() => {}), new Promise((r) => setTimeout(r, 1500))])
  }
  await sub.unsubscribe().catch(() => {})
}

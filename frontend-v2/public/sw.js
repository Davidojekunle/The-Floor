// The Floor's service worker. It only does browser push: no offline cache, the app needs the server anyway.
// Push payload (backend/app/services/push_service.py): { title, body, url, tag } where tag is the notification id.

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { title: event.data ? event.data.text() : '' }
  }
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      // The Floor is open and in front: the bell already shows it, so don't pop up over the app.
      if (windows.some((w) => w.visibilityState === 'visible' && w.focused)) return
      await self.registration.showNotification(data.title || 'The Floor', {
        body: data.body || undefined,
        tag: data.tag, // the same notification never shows twice
        icon: '/icon-192.png',
        badge: '/badge-72.png',
        data: { url: data.url || '/notifications', id: data.tag },
      })
    })(),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const { url = '/notifications', id } = event.notification.data || {}
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      const open = windows.find((w) => new URL(w.url).origin === self.location.origin)
      if (open) {
        await open.focus()
        open.postMessage({ type: 'open-notification', url, id }) // the app routes there and marks it read
        return
      }
      const target = new URL(url, self.location.origin)
      if (id) target.searchParams.set('n', id) // read on arrival (see usePushRouting)
      await self.clients.openWindow(target.href)
    })(),
  )
})

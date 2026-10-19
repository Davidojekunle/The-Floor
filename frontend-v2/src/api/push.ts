import { apiRequest } from './client'

export const getPushConfig = () => apiRequest<{ public_key: string }>('/push/config')

/** PushSubscription.toJSON(): idempotent, the app sends it again on each start while push is on. */
export const savePushSubscription = (sub: PushSubscriptionJSON) =>
  apiRequest<void>('/push/subscriptions', { method: 'POST', body: { endpoint: sub.endpoint, keys: sub.keys } })

export const removePushSubscription = (endpoint: string) =>
  apiRequest<void>('/push/subscriptions/remove', { method: 'POST', body: { endpoint } })

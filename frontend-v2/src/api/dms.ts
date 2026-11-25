import { apiRequest } from './client'

/** Private DMs (Me.direct_messages). New conversations need a shared room; once started they stay open. */
export type DmUser = { id: string; name: string }

export type DmMessage = {
  id: string
  sender_id: string
  body: string | null // null once deleted
  deleted: boolean
  created_at: string
}

export type DmThread = {
  id: string
  other: DmUser
  last_message: DmMessage | null
  last_message_at: string | null
  unread: number
  you_blocked: boolean // you blocked them
  can_send: boolean // false when either of you blocked the other
}

export type DmMessagePage = { items: DmMessage[]; has_more: boolean } // oldest first

export const listDmThreads = () => apiRequest<{ items: DmThread[] }>('/dms')
export const startDm = (userId: string) => apiRequest<DmThread>('/dms', { method: 'POST', body: { user_id: userId } })
export const getDmThread = (id: string) => apiRequest<DmThread>(`/dms/${id}`)
export const listDmMessages = (id: string, before?: string) =>
  apiRequest<DmMessagePage>(`/dms/${id}/messages`, { query: { before } })
export const sendDm = (id: string, body: string) =>
  apiRequest<DmMessage>(`/dms/${id}/messages`, { method: 'POST', body: { body } })
export const deleteDm = (id: string, messageId: string) =>
  apiRequest<void>(`/dms/${id}/messages/${messageId}`, { method: 'DELETE' })
export const markDmRead = (id: string) => apiRequest<void>(`/dms/${id}/read`, { method: 'POST' })
export const blockUser = (userId: string) => apiRequest<void>(`/blocks/${userId}`, { method: 'PUT' })
export const unblockUser = (userId: string) => apiRequest<void>(`/blocks/${userId}`, { method: 'DELETE' })

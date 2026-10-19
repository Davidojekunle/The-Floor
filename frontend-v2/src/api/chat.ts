import { apiRequest } from './client'
import type { UserBrief } from './rooms'

export type Ref = { id: string; title: string }

export type ChatEventType =
  | 'member_joined'
  | 'task_created'
  | 'task_approved'
  | 'stage_done'
  | 'stage_blocked'
  | 'stage_reopened'
  | 'task_completed'
  | 'temp_head_granted'
  | 'temp_head_revoked'
  | 'member_left'
  | 'head_transferred'

/** What a system message is about. `subject` is the person it's about when that isn't the actor. */
export type ChatEvent = {
  type: ChatEventType | (string & {})
  actor?: UserBrief | null
  subject?: UserBrief | null
  detail?: Record<string, unknown> | null // e.g. { reason } for stage_blocked, { expires_at } for temp_head_granted
}

export type Message = {
  id: string
  type: 'user' | 'system'
  sender: UserBrief | null
  body: string | null // null when deleted
  task: Ref | null // titles as they are now; null if deleted since
  stage: Ref | null
  event: ChatEvent | null
  created_at: string
  deleted: boolean
  can_delete: boolean
}

/** Always newest first. `has_more`: more exist in the direction asked. */
export type MessagePage = {
  items: Message[]
  has_more: boolean
  last_read_message_id: string | null
}

type ListOptions = { before?: string; after?: string; limit?: number; task_id?: string }

/**
 * - no cursor: the latest messages
 * - before: older than that message (scrolling up)
 * - after: the messages immediately after it (polling; repeat while has_more, nothing is skipped)
 */
export const listMessages = (roomId: string, opts: ListOptions = {}) =>
  apiRequest<MessagePage>(`/rooms/${roomId}/messages`, { query: { limit: 50, ...opts } })

export const sendMessage = (roomId: string, body: { body: string; task_id?: string; stage_id?: string }) =>
  apiRequest<Message>(`/rooms/${roomId}/messages`, { method: 'POST', body })

/** Soft delete: the message stays in place as "deleted". Safe to repeat. */
export const deleteMessage = (roomId: string, messageId: string) =>
  apiRequest<void>(`/rooms/${roomId}/messages/${messageId}`, { method: 'DELETE' })

/** Mark messages read up to (and including) this one, so nothing arriving later is marked read unseen. */
export const markMessagesRead = (roomId: string, upTo?: string) =>
  apiRequest<void>(`/rooms/${roomId}/messages/read`, { method: 'POST', body: upTo ? { up_to: upTo } : {} })

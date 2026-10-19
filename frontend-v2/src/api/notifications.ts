import { apiRequest } from './client'

export type NotificationType =
  | 'join_requested'
  | 'proposal_submitted'
  | 'stages_unassigned'
  | 'join_approved'
  | 'proposal_approved'
  | 'proposal_rejected'
  | 'temp_head_granted'
  | 'head_transferred'
  | 'removed_from_room'
  | 'room_deleted'
  | 'stage_ready'
  | 'stage_assigned'
  | 'mentioned'
  | 'replied'
  | 'nudged'
  | 'nudge_answered'
  | 'stage_due_soon'
  | 'stage_overdue'

type Named = { id: string; name: string }
type Titled = { id: string; title: string }

export type Notification = {
  id: string
  type: NotificationType | (string & {})
  title: string // ready to show: "Femi asked to join Studio Alpha"
  room: Named | null // may be a room that's gone (room_deleted, removed_from_room)
  task: Titled | null
  stage: Titled | null
  actor: Named | null
  /** proposal_rejected: {reason}. temp_head_granted: {expires_at}. stages_unassigned: {stages: [...]}. */
  data: {
    reason?: string
    expires_at?: string
    preview?: string // mentioned: what was said
    note?: string | null // nudged: the head's optional note
    kind?: 'update' | 'block' // nudged
    result_url?: string // stage_ready: the finished work from the stage before
    result_stage?: string
    message_id?: string
    stages?: { task_id: string; task_title: string; stage_id: string; stage_title: string }[]
  } | null
  created_at: string
  read: boolean
}

export type NotificationPage = { items: Notification[]; has_more: boolean }

/** Newest first. Page on with `before` = the last item's id. */
export const listNotifications = (opts: { unread?: boolean; before?: string; limit?: number } = {}) =>
  apiRequest<NotificationPage>('/me/notifications', { query: { limit: 30, ...opts, unread: opts.unread || undefined } })

/** Marks this one and everything older read; with no id, everything. */
export const markNotificationsRead = (upTo?: string) =>
  apiRequest<void>('/me/notifications/read', { method: 'POST', body: upTo ? { up_to: upTo } : {} })

export const markNotificationRead = (id: string) => apiRequest<void>(`/me/notifications/${id}/read`, { method: 'POST' })

export type NotificationSettings = {
  email_enabled: boolean // master switch for notification emails (security emails always go)
  requests: boolean
  decisions: boolean
  assignments: boolean
  daily_digest: boolean
  mentions: boolean // @mentions: bell, email and push
  all_messages: boolean // a push for every chat message (push only)
  muted_rooms: string[] // no emails and no bell items from these rooms
}

export const getNotificationSettings = () => apiRequest<NotificationSettings>('/me/notification-settings')

/** Send only the switches that change (not muted_rooms). */
export const updateNotificationSettings = (body: Partial<Omit<NotificationSettings, 'muted_rooms'>>) =>
  apiRequest<NotificationSettings>('/me/notification-settings', { method: 'PATCH', body })

/** One room at a time, so two tabs can't overwrite each other. Safe to repeat. */
export const muteRoom = (roomId: string) =>
  apiRequest<NotificationSettings>(`/me/notification-settings/muted-rooms/${roomId}`, { method: 'PUT' })
export const unmuteRoom = (roomId: string) =>
  apiRequest<NotificationSettings>(`/me/notification-settings/muted-rooms/${roomId}`, { method: 'DELETE' })

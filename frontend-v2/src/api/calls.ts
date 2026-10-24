import { apiRequest } from './client'
import type { UserBrief } from './rooms'

/** On /me rooms and task detail: a call is live there. */
export type LiveCall = { id: string; participant_count: number }

export type Call = {
  id: string
  room_id: string
  task: { id: string; title: string } | null
  kind: 'instant' | 'scheduled'
  status: 'scheduled' | 'live' | 'ended' | 'cancelled'
  missed: boolean
  title: string
  description: string | null
  starts_at: string | null // meetings: the planned start
  ends_at_planned: string | null
  started_at: string | null
  ended_at: string | null
  joinable_from: string // meetings: 10 minutes before the start
  created_by: UserBrief | null
  participants: UserBrief[] // who's in right now (only while live)
  attended: UserBrief[] // everyone who joined (the call log)
  duration_minutes: number | null // how long it ran; a meeting's planned length while scheduled
  invite: MeetingInvite | null // meetings only
  repeats: boolean // part of a repeating series
  external_url: string | null // a pasted Meet or Zoom link
  can_end: boolean // starter, head or temp head: may press End for everyone
  can_edit: boolean // a scheduled meeting this person may change or cancel
}

export type MeetingInvite = { everyone: boolean; users: UserBrief[]; tags: { id: string; name: string }[] }

export type InviteIn = { everyone: boolean; user_ids: string[]; tag_ids: string[] }

export type MeetingIn = {
  title: string
  description?: string | null
  starts_at: string // ISO with timezone
  duration_minutes: number
  task_id?: string | null
  invite: InviteIn
  external_url?: string | null
  repeat?: { every: 'week' | '2weeks'; until: string } | null // until: "YYYY-MM-DD"
}

export type Clash = { user: UserBrief; title: string; starts_at: string; room_name: string }

/** This person's own pass into the call. */
export type JoinPass =
  | { provider: 'livekit'; server_url: string; token: string; expires_at: string }
  | { provider: 'link'; url: string } // a meeting with a pasted Meet or Zoom link

/** Start a call in the room (or about a task). If one is already live there, that one comes back. */
export const startCall = (roomId: string, taskId?: string) =>
  apiRequest<Call>(`/rooms/${roomId}/calls`, { method: 'POST', body: taskId ? { task_id: taskId } : {} })

export const getCall = (roomId: string, callId: string) => apiRequest<Call>(`/rooms/${roomId}/calls/${callId}`)

export const joinCall = (roomId: string, callId: string) =>
  apiRequest<JoinPass>(`/rooms/${roomId}/calls/${callId}/join`, { method: 'POST' })

/** The room's call log and meetings, newest first. */
export const listCalls = (
  roomId: string,
  q: { status?: Call['status']; task_id?: string; from?: string; to?: string; page?: number; limit?: number } = {},
) => apiRequest<{ items: Call[]; total: number; page: number; limit: number }>(`/rooms/${roomId}/calls`, { query: q })

/** My calendar: meetings I'm invited to, and calls live now, across my rooms. */
export const listMyCalls = (from: string, to: string) =>
  apiRequest<{ items: Call[] }>('/me/calls', { query: { from, to } })

export const scheduleMeeting = (roomId: string, body: MeetingIn) =>
  apiRequest<Call>(`/rooms/${roomId}/meetings`, { method: 'POST', body })

export const updateMeeting = (roomId: string, callId: string, body: Partial<MeetingIn>) =>
  apiRequest<Call>(`/rooms/${roomId}/meetings/${callId}`, { method: 'PATCH', body })

export const cancelMeeting = (roomId: string, callId: string, following = false) =>
  apiRequest<void>(`/rooms/${roomId}/meetings/${callId}`, { method: 'DELETE', query: { following } })

/** Who already has a meeting then: a note for the form, never a block. */
export const checkClashes = (
  roomId: string,
  body: { starts_at: string; duration_minutes: number; invite: InviteIn; exclude_call_id?: string },
) => apiRequest<{ clashes: Clash[] }>(`/rooms/${roomId}/meetings/check`, { method: 'POST', body })

export const endCall = (roomId: string, callId: string) =>
  apiRequest<void>(`/rooms/${roomId}/calls/${callId}/end`, { method: 'POST' })

/** Copy for the call errors the server can send. */
export function callErrorText(code: string | undefined, fallback: string): string {
  switch (code) {
    case 'CALL_PROVIDER_UNAVAILABLE':
      return 'Calls are unavailable right now. Try again in a minute.'
    case 'CALL_NOT_OPEN':
      return fallback // the server says when it opens
    case 'CALL_ENDED':
      return 'This call has ended.'
    case 'CALL_FULL':
      return 'This call is full.'
    case 'TASK_NOT_APPROVED':
      return 'A call about a task can start once the task is approved.'
    case 'RATE_LIMITED':
      return 'Too many tries. Wait a moment and try again.'
    default:
      return fallback
  }
}

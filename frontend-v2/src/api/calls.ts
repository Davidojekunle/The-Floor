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
  started_at: string | null
  ended_at: string | null
  created_by: UserBrief | null
  participants: UserBrief[] // who's in right now (only while live)
  can_end: boolean // starter, head or temp head: may press End for everyone
}

/** This person's own pass into the call. */
export type JoinPass = { provider: 'livekit'; server_url: string; token: string; expires_at: string }

/** Start a call in the room (or about a task). If one is already live there, that one comes back. */
export const startCall = (roomId: string, taskId?: string) =>
  apiRequest<Call>(`/rooms/${roomId}/calls`, { method: 'POST', body: taskId ? { task_id: taskId } : {} })

export const getCall = (roomId: string, callId: string) => apiRequest<Call>(`/rooms/${roomId}/calls/${callId}`)

export const joinCall = (roomId: string, callId: string) =>
  apiRequest<JoinPass>(`/rooms/${roomId}/calls/${callId}/join`, { method: 'POST' })

export const endCall = (roomId: string, callId: string) =>
  apiRequest<void>(`/rooms/${roomId}/calls/${callId}/end`, { method: 'POST' })

/** Copy for the call errors the server can send. */
export function callErrorText(code: string | undefined, fallback: string): string {
  switch (code) {
    case 'CALL_PROVIDER_UNAVAILABLE':
      return 'Calls are unavailable right now. Try again in a minute.'
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

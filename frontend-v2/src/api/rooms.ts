import { apiRequest } from './client'
import type { RoomRole } from './auth'

export type Paginated<T> = {
  items: T[]
  total: number
  page: number
  limit: number
}

export type UserBrief = { id: string; name: string }

export type Room = {
  id: string
  name: string
  my_role: RoomRole
  temp_head_expires_at: string | null
  permissions: string[]
  member_count: number
  invite_code: string | null
  created_at: string
}

export type JoinPreview = {
  room_name: string
  member_count: number
  already_requested: boolean
  already_member: boolean
}

export type JoinRequestItem = {
  membership_id: string
  user: UserBrief
  requested_at: string
}

export type MembershipResult = {
  membership_id: string
  room_id: string
  status: 'pending' | 'active' | 'rejected' | 'removed'
}

export const createRoom = (name: string) => apiRequest<Room>('/rooms', { method: 'POST', body: { name } })

export const getRoom = (roomId: string) => apiRequest<Room>(`/rooms/${roomId}`)

/** Any member except the head (409 HEAD_MUST_TRANSFER). Tags, temp head and stage assignments here are cleared. */
export const leaveRoom = (roomId: string) => apiRequest<void>(`/rooms/${roomId}/leave`, { method: 'POST' })

/** Head only (`head.transfer`). The target becomes head and you become a member. Returns the room with your new role. */
export const transferHead = (roomId: string, membershipId: string) =>
  apiRequest<Room>(`/rooms/${roomId}/transfer-head`, { method: 'POST', body: { membership_id: membershipId } })

/** Head only (`room.delete`). Permanent. `confirmName` must match the room's name (case and spacing ignored). */
export const deleteRoom = (roomId: string, confirmName: string) =>
  apiRequest<void>(`/rooms/${roomId}`, { method: 'DELETE', body: { confirm_name: confirmName } })

export const getJoinPreview = (code: string) => apiRequest<JoinPreview>(`/join/${encodeURIComponent(code)}`)

export const requestToJoin = (code: string) =>
  apiRequest<MembershipResult>(`/join/${encodeURIComponent(code)}`, { method: 'POST' })

export const listJoinRequests = (roomId: string, page = 1) =>
  apiRequest<Paginated<JoinRequestItem>>(`/rooms/${roomId}/join-requests`, { query: { page, limit: 20 } })

export const approveJoinRequest = (roomId: string, membershipId: string) =>
  apiRequest<MembershipResult>(`/rooms/${roomId}/join-requests/${membershipId}/approve`, { method: 'POST' })

export const rejectJoinRequest = (roomId: string, membershipId: string) =>
  apiRequest<MembershipResult>(`/rooms/${roomId}/join-requests/${membershipId}/reject`, { method: 'POST' })

export const regenerateInvite = (roomId: string) =>
  apiRequest<{ invite_code: string }>(`/rooms/${roomId}/invite/regenerate`, { method: 'POST' })

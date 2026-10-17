import { apiRequest } from './client'
import type { RoomRole } from './auth'

export type Paginated<T> = {
  items: T[]
  total: number
  page: number
  limit: number
}

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
  user: { id: string; name: string }
  requested_at: string
}

export type MembershipResult = {
  membership_id: string
  room_id: string
  status: string
}

export function createRoom(name: string) {
  return apiRequest<Room>('/rooms', { method: 'POST', body: { name } })
}

export function getRoom(roomId: string) {
  return apiRequest<Room>(`/rooms/${roomId}`)
}

export function getJoinPreview(code: string) {
  return apiRequest<JoinPreview>(`/join/${encodeURIComponent(code)}`)
}

export function requestToJoin(code: string) {
  return apiRequest<MembershipResult>(`/join/${encodeURIComponent(code)}`, {
    method: 'POST',
  })
}

export function listJoinRequests(roomId: string, page = 1) {
  return apiRequest<Paginated<JoinRequestItem>>(
    `/rooms/${roomId}/join-requests`,
    { query: { page, limit: 20 } },
  )
}

export function approveJoinRequest(roomId: string, membershipId: string) {
  return apiRequest<MembershipResult>(
    `/rooms/${roomId}/join-requests/${membershipId}/approve`,
    { method: 'POST' },
  )
}

export function rejectJoinRequest(roomId: string, membershipId: string) {
  return apiRequest<MembershipResult>(
    `/rooms/${roomId}/join-requests/${membershipId}/reject`,
    { method: 'POST' },
  )
}
import { apiRequest } from './client'
import type { RoomRole } from './auth'
import type { Paginated, UserBrief } from './rooms'

export type TagBrief = { id: string; name: string }
export type Tag = TagBrief & { member_count: number }

export type Member = {
  membership_id: string
  user: UserBrief
  role: RoomRole // effective role
  temp_head_expires_at: string | null // set while they're an active temp head
  status: 'active'
  tags: TagBrief[]
  joined_at: string | null
}

export const listMembers = (roomId: string) =>
  apiRequest<Paginated<Member>>(`/rooms/${roomId}/members`, { query: { limit: 100 } })

export const setMemberTags = (roomId: string, membershipId: string, tagIds: string[]) =>
  apiRequest<Member>(`/rooms/${roomId}/members/${membershipId}`, { method: 'PATCH', body: { tag_ids: tagIds } })

export const removeMember = (roomId: string, membershipId: string) =>
  apiRequest<void>(`/rooms/${roomId}/members/${membershipId}`, { method: 'DELETE' })

/**
 * Make a member a temporary head until `expiresAt`, or change the end of an existing grant.
 * Head only. Up to the end of the 90th day from today (in the head's profile timezone).
 */
export const setTempHead = (roomId: string, membershipId: string, expiresAt: string) =>
  apiRequest<Member>(`/rooms/${roomId}/members/${membershipId}/temp-head`, { method: 'PUT', body: { expires_at: expiresAt } })

/** End a temporary head grant now. Safe to repeat. */
export const revokeTempHead = (roomId: string, membershipId: string) =>
  apiRequest<void>(`/rooms/${roomId}/members/${membershipId}/temp-head`, { method: 'DELETE' })

export const listTags = (roomId: string) => apiRequest<Paginated<Tag>>(`/rooms/${roomId}/tags`)

export const createTag = (roomId: string, name: string) =>
  apiRequest<Tag>(`/rooms/${roomId}/tags`, { method: 'POST', body: { name } })

export const renameTag = (roomId: string, tagId: string, name: string) =>
  apiRequest<Tag>(`/rooms/${roomId}/tags/${tagId}`, { method: 'PATCH', body: { name } })

export const deleteTag = (roomId: string, tagId: string) =>
  apiRequest<void>(`/rooms/${roomId}/tags/${tagId}`, { method: 'DELETE' })

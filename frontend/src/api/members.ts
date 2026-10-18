import { apiRequest } from './client'
import type { RoomRole } from './auth'
import type { Paginated } from './room'

export type Tag = { id: string; name: string; member_count: number }
export type TagRef = { id: string; name: string }

export type Member = {
  membership_id: string
  user: { id: string; name: string }
  role: RoomRole
  status: string
  tags: TagRef[]
  joined_at: string
}

export function listTags(roomId: string) {
  return apiRequest<Paginated<Tag>>(`/rooms/${roomId}/tags`, {
    query: { limit: 100 },
  })
}

export function createTag(roomId: string, name: string) {
  return apiRequest<Tag>(`/rooms/${roomId}/tags`, {
    method: 'POST',
    body: { name },
  })
}

export function renameTag(roomId: string, tagId: string, name: string) {
  return apiRequest<Tag>(`/rooms/${roomId}/tags/${tagId}`, {
    method: 'PATCH',
    body: { name },
  })
}

export function deleteTag(roomId: string, tagId: string) {
  return apiRequest<void>(`/rooms/${roomId}/tags/${tagId}`, {
    method: 'DELETE',
  })
}

export function listMembers(roomId: string, page = 1) {
  return apiRequest<Paginated<Member>>(`/rooms/${roomId}/members`, {
    query: { page, limit: 50 },
  })
}

export function setMemberTags(
  roomId: string,
  membershipId: string,
  tagIds: string[],
) {
  return apiRequest<Member>(`/rooms/${roomId}/members/${membershipId}`, {
    method: 'PATCH',
    body: { tag_ids: tagIds },
  })
}

export function removeMember(roomId: string, membershipId: string) {
  return apiRequest<void>(`/rooms/${roomId}/members/${membershipId}`, {
    method: 'DELETE',
  })
}
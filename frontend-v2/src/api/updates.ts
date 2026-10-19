import { apiRequest } from './client'
import type { Ref } from './chat'
import type { UserBrief } from './rooms'

/** A short note on a stage ("Shot 3 of 5 scenes"), with an optional web link. */
export type ProgressUpdate = {
  id: string
  stage: Ref
  author: UserBrief
  note: string
  link_url: string | null
  created_at: string
  can_delete: boolean // the author, or anyone with stage.edit
}

/** Always newest first. `has_more`: older updates exist (ask again with `before` = the last id). */
export type UpdatePage = { items: ProgressUpdate[]; has_more: boolean }

export type UpdateInput = {
  note: string // 1–2000 characters
  link_url?: string | null // http(s) only
  share_to_chat?: boolean // also posts the note (and link) to room chat, linked to this stage
}

type PageOptions = { before?: string; limit?: number }

const base = (roomId: string, taskId: string) => `/rooms/${roomId}/tasks/${taskId}`

export const listStageUpdates = (roomId: string, taskId: string, stageId: string, opts: PageOptions = {}) =>
  apiRequest<UpdatePage>(`${base(roomId, taskId)}/stages/${stageId}/updates`, { query: { limit: 20, ...opts } })

/** Every stage's updates in one feed. */
export const listTaskUpdates = (roomId: string, taskId: string, opts: PageOptions = {}) =>
  apiRequest<UpdatePage>(`${base(roomId, taskId)}/updates`, { query: { limit: 20, ...opts } })

/** Approved tasks only (409 TASK_NOT_APPROVED). Stage participants, or anyone with stage.edit. */
export const postUpdate = (roomId: string, taskId: string, stageId: string, body: UpdateInput) =>
  apiRequest<ProgressUpdate>(`${base(roomId, taskId)}/stages/${stageId}/updates`, { method: 'POST', body })

/** Safe to repeat. A copy shared to chat is a separate message and stays. */
export const deleteUpdate = (roomId: string, taskId: string, stageId: string, updateId: string) =>
  apiRequest<void>(`${base(roomId, taskId)}/stages/${stageId}/updates/${updateId}`, { method: 'DELETE' })

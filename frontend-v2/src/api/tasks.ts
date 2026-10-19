import { apiRequest } from './client'
import type { TagBrief } from './members'
import type { Paginated, UserBrief } from './rooms'

export type StageStatus = 'locked' | 'todo' | 'in_progress' | 'blocked' | 'done'
export type TaskStatus = 'not_started' | 'in_progress' | 'done'

export type Stage = {
  id: string
  title: string
  position: number
  step: number
  parallel_with_previous: boolean
  status: StageStatus
  blocked_reason: string | null
  unlocked_early: boolean
  tag: TagBrief | null
  assignees: UserBrief[]
  due_date: string | null
  is_overdue: boolean
  completed_at: string | null
  completed_by: UserBrief | null
  involves_me: boolean
  allowed_statuses: StageStatus[]
  can_update_status: boolean
  update_count: number // progress updates posted on this stage (phase 6b)
  /** The last nudge. Shown to the people on the stage and to heads. */
  nudge: { at: string; by: UserBrief | null; kind: 'update' | 'block'; note: string | null; open: boolean } | null
  nudge_kind: 'update' | 'block' | null // heads only: what a nudge would be now (late/stuck, or blocked)
  can_nudge: boolean // heads only, and not nudged in the last day
}

export type ApprovalStatus = 'pending' | 'approved' | 'rejected'

export type TaskListItem = {
  id: string
  title: string
  start_date: string | null
  due_date: string
  approval_status: ApprovalStatus
  status: TaskStatus
  progress: number
  stages_done: number
  stages_total: number
  current_stage_title: string | null
  is_overdue: boolean
  is_blocked: boolean
  involves_me: boolean
  created_by: UserBrief
  submitted_at: string | null // set on create and on resubmit
  decided_at: string | null
  rejection_reason: string | null
}

export type TaskDetail = TaskListItem & {
  room_id: string
  description: string | null
  current_stage_ids: string[]
  created_at: string
  updated_at: string
  completed_at: string | null
  approved_by: UserBrief | null
  decided_by: UserBrief | null
  // What I may do with this task. Drive the UI from these, not from roles (proposers get rights their room role lacks).
  can_edit: boolean
  can_delete: boolean
  can_resubmit: boolean
  can_decide: boolean
  stages: Stage[]
}

export type StageInput = {
  title: string
  tag_id?: string | null
  assignee_ids?: string[]
  due_date?: string | null
  parallel_with_previous?: boolean
}

export type TaskInput = {
  title: string
  description?: string | null
  start_date?: string | null
  due_date: string
  stages: StageInput[]
}

export type TaskFilters = {
  assignee?: 'me'
  overdue?: boolean
  blocked?: boolean
  status?: TaskStatus
  from?: string // calendar window [from, to), ISO UTC
  to?: string
  approval_status?: string // e.g. 'pending,rejected'; default 'approved'
  sort?: 'due_date' | 'submitted_at'
}

export type TaskUpdate = {
  title?: string
  description?: string | null
  start_date?: string | null
  due_date?: string
}

/** Only the fields sent change. assignee_ids replaces the whole set. */
export type StageUpdate = {
  title?: string
  tag_id?: string | null
  assignee_ids?: string[]
  due_date?: string | null
  parallel_with_previous?: boolean
  position?: number
}

export type TemplateInput = {
  name: string
  stages: { title: string; tag_id: string | null; parallel_with_previous: boolean }[]
}

export type Template = {
  id: string
  name: string
  stages: { position: number; title: string; tag: TagBrief | null; parallel_with_previous: boolean }[]
}

export const listTasks = (roomId: string, filters: TaskFilters = {}) =>
  apiRequest<Paginated<TaskListItem>>(`/rooms/${roomId}/tasks`, { query: { ...filters, limit: 500 } })

export const updateTask = (roomId: string, taskId: string, body: TaskUpdate) =>
  apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}`, { method: 'PATCH', body })

export const addStage = (roomId: string, taskId: string, body: StageInput & { position?: number }) =>
  apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}/stages`, { method: 'POST', body })

export const updateStage = (roomId: string, taskId: string, stageId: string, body: StageUpdate) =>
  apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}/stages/${stageId}`, { method: 'PATCH', body })

export const deleteStage = (roomId: string, taskId: string, stageId: string) =>
  apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}/stages/${stageId}`, { method: 'DELETE' })

export const getTask = (roomId: string, taskId: string) => apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}`)

export const createTask = (roomId: string, body: TaskInput) =>
  apiRequest<TaskDetail>(`/rooms/${roomId}/tasks`, { method: 'POST', body })

export const deleteTask = (roomId: string, taskId: string) =>
  apiRequest<void>(`/rooms/${roomId}/tasks/${taskId}`, { method: 'DELETE' })

/** Approve a pending or rejected proposal. Safe to repeat. */
export const approveTask = (roomId: string, taskId: string) =>
  apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}/approve`, { method: 'POST' })

/** Reject a pending proposal, with an optional reason (up to 500 characters) the proposer sees. */
export const rejectTask = (roomId: string, taskId: string, reason?: string) =>
  apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}/reject`, { method: 'POST', body: reason ? { reason } : undefined })

/** Send a rejected proposal back for approval. Only the proposer can. */
export const resubmitTask = (roomId: string, taskId: string) =>
  apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}/resubmit`, { method: 'POST' })

export const setStageStatus = (
  roomId: string,
  taskId: string,
  stageId: string,
  status: Exclude<StageStatus, 'locked'>,
  blockedReason?: string,
) =>
  apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}/stages/${stageId}/status`, {
    method: 'PUT',
    body: { status, blocked_reason: blockedReason ?? null },
  })

export const listTemplates = (roomId: string) => apiRequest<Paginated<Template>>(`/rooms/${roomId}/templates`)

export const createTemplate = (roomId: string, body: TemplateInput) =>
  apiRequest<Template>(`/rooms/${roomId}/templates`, { method: 'POST', body })

export const getTemplate = (roomId: string, templateId: string) =>
  apiRequest<Template>(`/rooms/${roomId}/templates/${templateId}`)

/** `stages` replaces the whole list. Tasks already made from the template don't change. */
export const updateTemplate = (roomId: string, templateId: string, body: Partial<TemplateInput>) =>
  apiRequest<Template>(`/rooms/${roomId}/templates/${templateId}`, { method: 'PATCH', body })

export const deleteTemplate = (roomId: string, templateId: string) =>
  apiRequest<void>(`/rooms/${roomId}/templates/${templateId}`, { method: 'DELETE' })

/** Heads: privately ask the people on a late, stuck or blocked stage for an update (once a day). */
export const nudgeStage = (roomId: string, taskId: string, stageId: string, note?: string) =>
  apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}/stages/${stageId}/nudge`, { method: 'POST', body: note ? { note } : {} })

/** “I'm on it”: starts a To do stage, or answers the nudge on one already in progress. */
export const ackNudge = (roomId: string, taskId: string, stageId: string) =>
  apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}/stages/${stageId}/nudge/ack`, { method: 'POST' })

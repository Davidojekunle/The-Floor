import { apiRequest } from './client'
import type { Paginated } from './room'
import {
  mockCreateTask,
  mockGetTask,
  mockListTasks,
  mockSetStageStatus,
} from '../mocks/tasks'
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'

export type StageStatus = 'locked' | 'todo' | 'in_progress' | 'blocked' | 'done'
export type TaskStatus = 'not_started' | 'in_progress' | 'done'

type PersonRef = { id: string; name: string }

export type Stage = {
  id: string
  title: string
  position: number
  step: number
  parallel_with_previous: boolean
  status: StageStatus
  blocked_reason: string | null
  unlocked_early: boolean
  tag: { id: string; name: string } | null
  assignees: PersonRef[]
  due_date: string | null
  is_overdue: boolean
  completed_at: string | null
  completed_by: PersonRef | null
  allowed_statuses: StageStatus[]
  can_update_status: boolean
}

export type TaskDetail = {
  id: string
  room_id: string
  title: string
  description: string | null
  start_date: string | null
  due_date: string
  approval_status: string
  status: TaskStatus
  progress: number
  stages_done: number
  stages_total: number
  current_stage_ids: string[]
  current_stage_title: string | null
  is_overdue: boolean
  is_blocked: boolean
  created_by: PersonRef
  created_at: string
  updated_at: string
  completed_at: string | null
  stages: Stage[]
}

export type TaskListItem = {
  id: string
  title: string
  start_date: string | null
  due_date: string
  approval_status: string
  status: TaskStatus
  progress: number
  stages_done: number
  stages_total: number
  current_stage_title: string | null
  is_overdue: boolean
  is_blocked: boolean
  involves_me: boolean
}

export type TaskListParams = {
  from?: string
  to?: string
  status?: string
  page?: number
  limit?: number
}

export function listTasks(roomId: string, params: TaskListParams = {}) {
  if (USE_MOCKS) return mockListTasks()
  return apiRequest<Paginated<TaskListItem>>(`/rooms/${roomId}/tasks`, {
    query: { ...params },
  })
}

export function getTask(roomId: string, taskId: string) {
  if (USE_MOCKS) return mockGetTask(taskId)
  return apiRequest<TaskDetail>(`/rooms/${roomId}/tasks/${taskId}`)
}

export function setStageStatus(
  roomId: string,
  taskId: string,
  stageId: string,
  status: StageStatus,
  blockedReason?: string,
) {
  if (USE_MOCKS) return mockSetStageStatus(taskId, stageId, status, blockedReason)
  return apiRequest<TaskDetail>(
    `/rooms/${roomId}/tasks/${taskId}/stages/${stageId}/status`,
    {
      method: 'POST',
      body: { status, blocked_reason: blockedReason },
    },
  )
}

export type CreateStageInput = {
  title: string
  tag_id: string | null
  assignee_ids: string[]
  due_date: string | null
  parallel_with_previous: boolean
}

export type CreateTaskInput = {
  title: string
  description: string | null
  start_date: string | null
  due_date: string
  stages: CreateStageInput[]
}

export function CreateTask(roomId: string, input: CreateTaskInput) {
  if (USE_MOCKS) return mockCreateTask(roomId, input)
  return apiRequest<TaskDetail>(`/rooms/${roomId}/tasks`, {
    method: 'POST',
    body: input,
  })
}
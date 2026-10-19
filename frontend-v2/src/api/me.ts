import { apiRequest } from './client'
import type { TagBrief } from './members'
import type { Paginated } from './rooms'
import type { StageStatus, TaskListItem, TaskStatus } from './tasks'

/** One of my stages inside a task, as returned by GET /me/tasks. */
export type MyStage = {
  id: string
  title: string
  status: StageStatus
  step: number
  due_date: string | null
  is_overdue: boolean
  allowed_statuses: StageStatus[]
  tag: TagBrief | null
  assigned_to_me: boolean // false = it reaches me through `tag`
  blocked_reason: string | null
}

export type MyTask = TaskListItem & {
  room: { id: string; name: string }
  my_stages: MyStage[]
}

export type MyTaskFilters = {
  scope?: 'mine' | 'all'
  actionable?: boolean
  room?: string
  from?: string
  to?: string
  status?: TaskStatus
  overdue?: boolean
  blocked?: boolean
  approval_status?: string // 'pending,rejected' = my own proposals across rooms
  sort?: 'due_date' | 'submitted_at'
}

export const listMyTasks = (filters: MyTaskFilters = {}) =>
  apiRequest<Paginated<MyTask>>('/me/tasks', { query: { ...filters, limit: 500 } })

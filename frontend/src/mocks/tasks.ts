import { ApiError } from '../api/client'
import { listMembers, listTags } from '../api/members'
import type { Paginated } from '../api/room'
import type {
  CreateTaskInput,
  Stage,
  StageStatus,
  TaskDetail,
  TaskListItem,
} from '../api/tasks'

const DAY = 24 * 60 * 60 * 1000
const iso = (days: number) => new Date(Date.now() + days * DAY).toISOString()
const person = (id: string, name: string) => ({ id, name })
const delay = () => new Promise((resolve) => setTimeout(resolve, 250))

type Seed = {
  title: string
  tag: string | null
  assignees: string[]
  due: number
  status: StageStatus
  parallel?: boolean
}

// What the head may do from each status (contract, section 2).
const HEAD_ALLOWED: Record<StageStatus, StageStatus[]> = {
  locked: ['todo', 'in_progress'],
  todo: ['in_progress', 'done'],
  in_progress: ['todo', 'done', 'blocked'],
  blocked: ['in_progress'],
  done: ['in_progress'],
}

function recompute(task: TaskDetail): TaskDetail {
  const now = Date.now()

  for (const stage of task.stages) {
    if (stage.status === 'locked') {
      const earlierDone = task.stages
        .filter((s) => s.step < stage.step)
        .every((s) => s.status === 'done')
      if (earlierDone) stage.status = 'todo'
    }
  }

  const done = task.stages.filter((s) => s.status === 'done').length
  const total = task.stages.length
  const steps = [...new Set(task.stages.map((s) => s.step))].sort((a, b) => a - b)
  const currentStep = steps.find((n) =>
    task.stages.some((s) => s.step === n && s.status !== 'done'),
  )
  const current = task.stages.filter((s) => s.step === currentStep)

  for (const s of task.stages) {
    s.allowed_statuses = HEAD_ALLOWED[s.status]
    s.can_update_status = s.allowed_statuses.length > 0
    s.is_overdue =
      s.due_date !== null &&
      s.status !== 'done' &&
      new Date(s.due_date).getTime() < now
  }

  task.stages_done = done
  task.stages_total = total
  task.progress = Math.round((100 * done) / total)
  task.current_stage_ids = current.map((s) => s.id)
  task.current_stage_title = current.length
    ? current.map((s) => s.title).join(', ')
    : null
  task.is_blocked = task.stages.some((s) => s.status === 'blocked')
  task.status =
    done === total
      ? 'done'
      : done > 0 ||
          task.stages.some(
            (s) => s.status === 'in_progress' || s.status === 'blocked',
          )
        ? 'in_progress'
        : 'not_started'
  task.is_overdue =
    task.status !== 'done' && new Date(task.due_date).getTime() < now
  return task
}

function makeTask(
  id: string,
  title: string,
  description: string,
  dueDays: number,
  seeds: Seed[],
): TaskDetail {
  let step = 0
  const stages: Stage[] = seeds.map((s, i) => {
    if (!s.parallel) step += 1
    return {
      id: `${id}-s${i + 1}`,
      title: s.title,
      position: i + 1,
      step,
      parallel_with_previous: Boolean(s.parallel),
      status: s.status,
      blocked_reason: null,
      unlocked_early: false,
      tag: s.tag ? { id: `tag-${s.tag}`, name: s.tag } : null,
      assignees: s.assignees.map((n) => person(`u-${n}`, n)),
      due_date: iso(s.due),
      is_overdue: false,
      completed_at: s.status === 'done' ? iso(-1) : null,
      completed_by: s.status === 'done' ? person('u-Femi', 'Femi') : null,
      allowed_statuses: [],
      can_update_status: false,
    }
  })

  return recompute({
    id,
    room_id: 'mock',
    title,
    description,
    start_date: null,
    due_date: iso(dueDays),
    approval_status: 'approved',
    status: 'not_started',
    progress: 0,
    stages_done: 0,
    stages_total: stages.length,
    current_stage_ids: [],
    current_stage_title: null,
    is_overdue: false,
    is_blocked: false,
    created_by: person('u1', 'Ada'),
    created_at: iso(-3),
    updated_at: iso(-1),
    completed_at: null,
    stages,
  })
}

const tasks: TaskDetail[] = [
  makeTask('k1', 'Product promo video', '30s cut for Instagram', 4, [
    { title: 'Script', tag: 'Content Writer', assignees: ['Femi'], due: -2, status: 'done' },
    { title: 'Shoot', tag: 'Videographer', assignees: ['Seun'], due: 1, status: 'in_progress' },
    { title: 'Edit', tag: 'Video Editor', assignees: [], due: 3, status: 'locked' },
  ]),
  makeTask('k2', 'Brand launch kit', 'Logo pack, music bed and final export', 10, [
    { title: 'Brief', tag: 'Content Writer', assignees: ['Femi'], due: 2, status: 'todo' },
    { title: 'Graphics', tag: 'Designer', assignees: ['Tola'], due: 6, status: 'locked' },
    { title: 'Music', tag: 'Sound', assignees: [], due: 6, status: 'locked', parallel: true },
    { title: 'Final export', tag: 'Video Editor', assignees: [], due: 9, status: 'locked' },
  ]),
  makeTask('k3', 'Weekly social posts', 'Three posts for this week', -1, [
    { title: 'Draft captions', tag: 'Content Writer', assignees: [], due: -2, status: 'in_progress' },
    { title: 'Design and post', tag: 'Designer', assignees: [], due: -1, status: 'locked' },
  ]),
]

function toListItem(t: TaskDetail): TaskListItem {
  return {
    id: t.id,
    title: t.title,
    start_date: t.start_date,
    due_date: t.due_date,
    approval_status: t.approval_status,
    status: t.status,
    progress: t.progress,
    stages_done: t.stages_done,
    stages_total: t.stages_total,
    current_stage_title: t.current_stage_title,
    is_overdue: t.is_overdue,
    is_blocked: t.is_blocked,
    involves_me: t.stages.some((s) => s.assignees.length > 0),
  }
}

function findTask(taskId: string): TaskDetail {
  const task = tasks.find((t) => t.id === taskId)
  if (!task) throw new ApiError(404, 'NOT_FOUND', 'Task not found.')
  return task
}

export async function mockListTasks(): Promise<Paginated<TaskListItem>> {
  await delay()
  const items = tasks
    .map(toListItem)
    .sort((a, b) => a.due_date.localeCompare(b.due_date))
  return { items, total: items.length, page: 1, limit: 50 }
}

export async function mockGetTask(taskId: string): Promise<TaskDetail> {
  await delay()
  return structuredClone(findTask(taskId))
}

export async function mockSetStageStatus(
  taskId: string,
  stageId: string,
  status: StageStatus,
  blockedReason?: string,
): Promise<TaskDetail> {
  await delay()
  const task = findTask(taskId)
  const stage = task.stages.find((s) => s.id === stageId)
  if (!stage) throw new ApiError(404, 'NOT_FOUND', 'Stage not found.')

  if (stage.status !== status) {
    if (!stage.allowed_statuses.includes(status)) {
      throw new ApiError(409, 'CONFLICT', 'That change is not allowed right now.')
    }
    if (status === 'blocked' && !blockedReason) {
      throw new ApiError(422, 'VALIDATION_ERROR', 'A reason is required.', {
        blocked_reason: 'A reason is required.',
      })
    }
    if (stage.status === 'locked' && status === 'todo') {
      stage.unlocked_early = true
    }
    stage.status = status
    stage.blocked_reason = status === 'blocked' ? (blockedReason ?? null) : null
    stage.completed_at = status === 'done' ? new Date().toISOString() : null
    stage.completed_by = status === 'done' ? person('u1', 'Ada') : null
    task.updated_at = new Date().toISOString()
    recompute(task)
  }
  return structuredClone(task)
}

export async function mockCreateTask(
  roomId: string,
  input: CreateTaskInput,
): Promise<TaskDetail> {
  await delay()

  const fields: Record<string, string> = {}
  if (input.start_date && input.start_date > input.due_date) {
    fields.start_date = 'The start must not be after the due date.'
  }
  input.stages.forEach((s, i) => {
    if (s.due_date && s.due_date > input.due_date) {
      fields[`stages.${i}.due_date`] = 'Must not be after the task due date.'
    }
  })
  if (Object.keys(fields).length > 0) {
    throw new ApiError(422, 'VALIDATION_ERROR', 'Validation failed.', fields)
  }

  const [tagsRes, membersRes] = await Promise.all([
    listTags(roomId),
    listMembers(roomId, 1, 100),
  ])
  const tagName = new Map(tagsRes.items.map((t) => [t.id, t.name]))
  const personName = new Map(membersRes.items.map((m) => [m.user.id, m.user.name]))

  const id = `k${Date.now()}`
  let step = 0
  const stages: Stage[] = input.stages.map((s, i) => {
    if (!s.parallel_with_previous) step += 1
    return {
      id: `${id}-s${i + 1}`,
      title: s.title,
      position: i + 1,
      step,
      parallel_with_previous: s.parallel_with_previous,
      status: 'locked',
      blocked_reason: null,
      unlocked_early: false,
      tag: s.tag_id
        ? { id: s.tag_id, name: tagName.get(s.tag_id) ?? 'Tag' }
        : null,
      assignees: s.assignee_ids.map((uid) =>
        person(uid, personName.get(uid) ?? 'Member'),
      ),
      due_date: s.due_date,
      is_overdue: false,
      completed_at: null,
      completed_by: null,
      allowed_statuses: [],
      can_update_status: false,
    }
  })

  const task = recompute({
    id,
    room_id: roomId,
    title: input.title,
    description: input.description,
    start_date: input.start_date,
    due_date: input.due_date,
    approval_status: 'approved',
    status: 'not_started',
    progress: 0,
    stages_done: 0,
    stages_total: stages.length,
    current_stage_ids: [],
    current_stage_title: null,
    is_overdue: false,
    is_blocked: false,
    created_by: person('u1', 'You'),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    completed_at: null,
    stages,
  })
  tasks.push(task)
  return structuredClone(task)
}
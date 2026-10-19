// Demo data shaped exactly like TaskListItem (see src/api/tasks.ts). Dates are relative to today
// so "overdue", "tomorrow" and "this week" stay true whenever the prototype is opened.
import type { TaskListItem } from '../../src/api/tasks'

const day = (offset: number) => {
  const d = new Date()
  d.setDate(d.getDate() + offset)
  d.setHours(22, 0, 0, 0)
  return d.toISOString()
}

type Seed = Pick<TaskListItem, 'title' | 'stages_done' | 'stages_total'> &
  Partial<TaskListItem> & { due: number }

const seeds: Seed[] = [
  { title: 'Spring catalogue print files', stages_done: 3, stages_total: 5, current_stage_title: 'Colour proofs', due: -2, is_overdue: true, involves_me: true },
  { title: 'Onboarding video for new hires', stages_done: 1, stages_total: 4, current_stage_title: 'Voiceover recording', due: 2, is_blocked: true },
  { title: 'Website footer refresh', stages_done: 2, stages_total: 3, current_stage_title: 'Copy review', due: 1, involves_me: true },
  { title: 'Q4 budget pack', stages_done: 0, stages_total: 6, current_stage_title: 'Collect department numbers', due: 4, status: 'not_started' },
  { title: 'Office move: floor plan', stages_done: 1, stages_total: 3, current_stage_title: 'Facilities sign-off, IT survey', due: 12 },
  { title: 'Brand guidelines v2', stages_done: 4, stages_total: 7, current_stage_title: 'Typography section', due: 20, involves_me: true },
  { title: 'Client workshop notes', stages_done: 4, stages_total: 4, current_stage_title: null, due: -5, status: 'done' },
  { title: 'Recruitment ad for junior designer', stages_done: 3, stages_total: 3, current_stage_title: null, due: -9, status: 'done' },
]

export const TASKS: TaskListItem[] = seeds.map(({ due, ...s }, i) => ({
  id: `proto-${i}`,
  start_date: day(due - 14),
  due_date: day(due),
  approval_status: 'approved',
  status: 'in_progress',
  progress: Math.round((s.stages_done / s.stages_total) * 100),
  current_stage_title: null,
  is_overdue: false,
  is_blocked: false,
  involves_me: false,
  ...s,
}))
  .map((t) => t as TaskListItem)
  .sort((a, b) => a.due_date.localeCompare(b.due_date))

export type Group = 'overdue' | 'week' | 'later' | 'done'
export const GROUPS: { key: Group; label: string }[] = [
  { key: 'overdue', label: 'Overdue' },
  { key: 'week', label: 'This week' },
  { key: 'later', label: 'Later' },
  { key: 'done', label: 'Done' },
]
const weekEnd = day(6)
export const groupOf = (t: TaskListItem): Group =>
  t.status === 'done' ? 'done' : t.is_overdue ? 'overdue' : t.due_date <= weekEnd ? 'week' : 'later'

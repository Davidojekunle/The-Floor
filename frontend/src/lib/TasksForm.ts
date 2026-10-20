import type { CreateTaskInput } from '../api/tasks'

export type StageDraft = {
  key: string
  title: string
  tagId: string
  assigneeIds: string[]
  due: string
  parallel: boolean
}

export type TaskDraft = {
  title: string
  description: string
  start: string
  due: string
  stages: StageDraft[]
}

export function newStageDraft(): StageDraft {
  return {
    key: crypto.randomUUID(),
    title: '',
    tagId: '',
    assigneeIds: [],
    due: '',
    parallel: false,
  }
}

// "2026-10-30T17:00" (local time from a datetime-local input) to a UTC ISO string.
export function localToIso(value: string): string | null {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

export function buildCreateInput(draft: TaskDraft): CreateTaskInput {
  return {
    title: draft.title.trim(),
    description: draft.description.trim() || null,
    start_date: localToIso(draft.start),
    due_date: localToIso(draft.due) ?? '',
    stages: draft.stages.map((s, i) => ({
      title: s.title.trim(),
      tag_id: s.tagId || null,
      assignee_ids: s.assigneeIds,
      due_date: localToIso(s.due),
      parallel_with_previous: i === 0 ? false : s.parallel,
    })),
  }
}
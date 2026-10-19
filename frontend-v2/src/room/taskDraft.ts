import type { Stage } from '../api/tasks'
import { dayInput, dayKey } from '../lib/dates'

/**
 * Who does a stage, as one select value:
 * '' nobody yet · 'tag:<id>' everyone with a tag · 'user:<id>' one person ·
 * 'keep' an existing mix (tag + people, or several people) that the form leaves untouched.
 */
export type Owner = string

export type DraftStage = {
  key: number
  id?: string // set for stages that already exist (edit)
  title: string
  owner: Owner
  keepLabel?: string // shown for owner 'keep'
  due: string // "YYYY-MM-DD" or ''
  showDue: boolean
  parallel: boolean
}

export type DraftTask = {
  title: string
  due: string // "YYYY-MM-DD"
  description: string | null // null = field hidden
  stages: DraftStage[]
}

/** Thrown by onSubmit to put messages on specific fields, e.g. { 'stages.1.due_date': '…' }. */
export class FieldErrors extends Error {
  fields: Record<string, string>
  constructor(fields: Record<string, string>) {
    super('Some fields are invalid.')
    this.fields = fields
  }
}

let nextKey = 1
export const newStage = (patch: Partial<DraftStage> = {}): DraftStage => ({
  key: nextKey++,
  title: '',
  owner: '',
  due: '',
  showDue: false,
  parallel: false,
  ...patch,
})

/** A blank form with one empty stage and a due date a week out. */
export function blankDraft(timeZone: string): DraftTask {
  return { title: '', due: dayInput(timeZone, 7), description: null, stages: [newStage()] }
}

/** API fields for an owner value. 'keep' sends nothing so the stage stays as it is. */
export function ownerFields(owner: Owner): { tag_id?: string | null; assignee_ids?: string[] } {
  if (owner === 'keep') return {}
  return {
    tag_id: owner.startsWith('tag:') ? owner.slice(4) : null,
    assignee_ids: owner.startsWith('user:') ? [owner.slice(5)] : [],
  }
}

/** The owner value for an existing stage. */
export function ownerOf(stage: Stage): { owner: Owner; keepLabel?: string } {
  const people = stage.assignees
  if (stage.tag && people.length === 0) return { owner: `tag:${stage.tag.id}` }
  if (!stage.tag && people.length === 1) return { owner: `user:${people[0].id}` }
  if (!stage.tag && people.length === 0) return { owner: '' }
  const label = [stage.tag?.name, ...people.map((p) => p.name)].filter(Boolean).join(' + ')
  return { owner: 'keep', keepLabel: `Keep: ${label}` }
}

/** Form state for an existing task. */
export function draftFromTask(
  task: { title: string; due_date: string; description: string | null; stages: Stage[] },
  timeZone: string,
): DraftTask {
  return {
    title: task.title,
    due: dayKey(task.due_date, timeZone),
    description: task.description,
    stages: task.stages.map((s) =>
      newStage({
        id: s.id,
        title: s.title,
        ...ownerOf(s),
        due: s.due_date ? dayKey(s.due_date, timeZone) : '',
        showDue: !!s.due_date,
        parallel: s.parallel_with_previous,
      }),
    ),
  }
}

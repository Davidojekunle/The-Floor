import type { RoomRole } from '../api/auth'
import type { StageStatus } from '../api/tasks'

// Unknown values from a newer backend fall back to a safe label instead of crashing.
export const roleLabel = (role: RoomRole | string) =>
  ({ head: 'Head', temp_head: 'Temp head', member: 'Member' })[role as RoomRole] ?? 'Member'

export const statusLabel = (status: StageStatus | string) =>
  ({ locked: 'Locked', todo: 'To do', in_progress: 'In progress', blocked: 'Blocked', done: 'Done' })[
    status as StageStatus
  ] ?? status

/** Button text for moving a stage from one status to another. */
export const TRANSITION_LABEL: Record<string, string> = {
  'todo>in_progress': 'Start',
  'todo>done': 'Mark done',
  'in_progress>done': 'Mark done',
  'in_progress>blocked': 'Report a blocker',
  'in_progress>todo': 'Move back to To do',
  'blocked>in_progress': 'Clear blocker',
  'locked>todo': 'Unlock early',
  'locked>in_progress': 'Unlock and start',
  'done>in_progress': 'Reopen',
}

/** The one transition shown as a button; the rest go in the "…" menu. */
export const PRIMARY_TRANSITION: Partial<Record<StageStatus, StageStatus>> = {
  todo: 'in_progress',
  in_progress: 'done',
  blocked: 'in_progress',
  locked: 'todo',
  done: 'in_progress',
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

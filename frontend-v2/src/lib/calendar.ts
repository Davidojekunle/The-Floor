import { addDays, monthGrid, startOfDayIso } from './dates'

export type CalendarEvent = {
  id: string
  title: string
  due: string // ISO UTC
  href: string
  state: 'overdue' | 'blocked' | 'done' | 'open'
  detail?: string // e.g. room name or current stage
}

/** The query window for a month view, in the user's timezone: [first grid day, day after last). */
export function calendarWindow(month: string, timeZone: string) {
  const days = monthGrid(month)
  return { from: startOfDayIso(days[0], timeZone), to: startOfDayIso(addDays(days[41], 1), timeZone) }
}

type TaskLike = {
  id: string
  title: string
  due_date: string
  status: string
  is_overdue: boolean
  is_blocked: boolean
  current_stage_title: string | null
}

/** Map a task list item to a calendar event. */
export function toEvent(t: TaskLike, href: string, detail?: string): CalendarEvent {
  const state = t.status === 'done' ? 'done' : t.is_overdue ? 'overdue' : t.is_blocked ? 'blocked' : 'open'
  return {
    id: t.id,
    title: t.title,
    due: t.due_date,
    href,
    state,
    detail: detail ?? (t.current_stage_title ? `Now: ${t.current_stage_title}` : undefined),
  }
}

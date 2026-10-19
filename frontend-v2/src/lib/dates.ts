// All API dates are UTC. We display them in the user's PROFILE timezone (/me.timezone), not the browser's.

type Parts = { y: number; m: number; d: number; h: number; min: number; s: number }

function partsIn(date: Date, timeZone: string): Parts {
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
    second: 'numeric',
  })
  const p = Object.fromEntries(fmt.formatToParts(date).map((x) => [x.type, Number(x.value)]))
  return { y: p.year, m: p.month, d: p.day, h: p.hour, min: p.minute, s: p.second }
}

/** Milliseconds the zone is ahead of UTC at that instant. */
function offsetMs(instant: number, timeZone: string): number {
  const p = partsIn(new Date(instant), timeZone)
  return Date.UTC(p.y, p.m - 1, p.d, p.h, p.min, p.s) - Math.floor(instant / 1000) * 1000
}

/** The UTC instant of a wall-clock time on a day in the zone. */
function zonedIso(day: string, timeZone: string, h: number, min: number, s: number): string {
  const [y, m, d] = day.split('-').map(Number)
  const wallClock = Date.UTC(y, m - 1, d, h, min, s)
  let instant = wallClock - offsetMs(wallClock, timeZone)
  instant = wallClock - offsetMs(instant, timeZone) // second pass handles DST changes
  return new Date(instant).toISOString()
}

/**
 * A picked day ("2026-10-24") means 23:59:59 on that day in the user's PROFILE timezone, as UTC.
 * Agreed with the backend on 2026-10-18. Same rule for stage due dates.
 */
export const endOfDayIso = (day: string, timeZone: string) => zonedIso(day, timeZone, 23, 59, 59)

/** Midnight at the start of a day in the zone, as UTC. Used for calendar windows. */
export const startOfDayIso = (day: string, timeZone: string) => zonedIso(day, timeZone, 0, 0, 0)

/** The day ("2026-10-24") an instant falls on in the zone. */
export function dayKey(iso: string, timeZone: string): string {
  const p = partsIn(new Date(iso), timeZone)
  return `${p.y}-${String(p.m).padStart(2, '0')}-${String(p.d).padStart(2, '0')}`
}

/** Add days to a "YYYY-MM-DD" day. */
export function addDays(day: string, n: number): string {
  const [y, m, d] = day.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10)
}

/** The 6-week Monday-first grid that shows a month. `month` is "YYYY-MM". */
export function monthGrid(month: string): string[] {
  const [y, m] = month.split('-').map(Number)
  const first = new Date(Date.UTC(y, m - 1, 1))
  const back = (first.getUTCDay() + 6) % 7 // days since Monday
  const start = addDays(first.toISOString().slice(0, 10), -back)
  return Array.from({ length: 42 }, (_, i) => addDays(start, i))
}

/** "October 2026" */
export function monthLabel(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(
    new Date(Date.UTC(y, m - 1, 1)),
  )
}

/** Shift "YYYY-MM" by n months. */
export function addMonths(month: string, n: number): string {
  const [y, m] = month.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1 + n, 1)).toISOString().slice(0, 7)
}

/** "2026-10-24" for today + n days, in the user's timezone. For date inputs. */
export function dayInput(timeZone: string, addDays = 0): string {
  const p = partsIn(new Date(), timeZone)
  const dt = new Date(Date.UTC(p.y, p.m - 1, p.d + addDays))
  return dt.toISOString().slice(0, 10)
}

function dayNumber(date: Date, timeZone: string): number {
  const p = partsIn(date, timeZone)
  return Date.UTC(p.y, p.m - 1, p.d) / 86_400_000
}

/** "Fri, Oct 24" */
export function formatDay(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone, weekday: 'short', month: 'short', day: 'numeric' }).format(
    new Date(iso),
  )
}

/** "Due today", "Due tomorrow", "Due Fri, Oct 24", or "3 days overdue" when late. */
export function dueLabel(iso: string, timeZone: string, overdue = false): string {
  const diff = dayNumber(new Date(iso), timeZone) - dayNumber(new Date(), timeZone)
  if (overdue) {
    const late = Math.max(0, -diff)
    return late === 0 ? 'Overdue today' : late === 1 ? '1 day overdue' : `${late} days overdue`
  }
  if (diff === 0) return 'Due today'
  if (diff === 1) return 'Due tomorrow'
  return `Due ${formatDay(iso, timeZone)}`
}

/** "2 hours ago", "yesterday", "Oct 15" */
export function relativeTime(iso: string, timeZone: string): string {
  const then = new Date(iso)
  const mins = Math.round((Date.now() - then.getTime()) / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return mins === 1 ? '1 minute ago' : `${mins} minutes ago`
  const hours = Math.round(mins / 60)
  const days = dayNumber(new Date(), timeZone) - dayNumber(then, timeZone)
  if (days === 0) return hours === 1 ? '1 hour ago' : `${hours} hours ago`
  if (days === 1) return 'yesterday'
  return new Intl.DateTimeFormat('en-US', { timeZone, month: 'short', day: 'numeric' }).format(then)
}

// Three task-row directions. Each renders only fields TaskListItem really has.
import type { TaskListItem } from '../../src/api/tasks'
import { Icon } from '../../src/components/Icon'
import { dueLabel } from '../../src/lib/dates'

type RowProps = { task: TaskListItem; tz: string }

const state = (t: TaskListItem) =>
  t.status === 'done' ? 'done' : t.is_overdue ? 'late' : t.is_blocked ? 'blocked' : t.status === 'not_started' ? 'idle' : 'moving'

const dayParts = (iso: string, timeZone: string) => {
  const d = new Date(iso)
  return {
    wd: new Intl.DateTimeFormat('en-US', { timeZone, weekday: 'short' }).format(d),
    n: new Intl.DateTimeFormat('en-US', { timeZone, day: 'numeric' }).format(d),
    mon: new Intl.DateTimeFormat('en-US', { timeZone, month: 'short' }).format(d),
  }
}

/* 1. Ledger: a printed schedule. The date leads, stages are counted as ticks, hairlines instead of a box. */
export function LedgerRow({ task: t, tz }: RowProps) {
  const s = state(t)
  const d = dayParts(t.due_date, tz)
  const ticks = t.stages_total <= 12
  return (
    <a className={`lg-row is-${s}`} href="#">
      <span className="lg-date" aria-label={dueLabel(t.due_date, tz, t.is_overdue)}>
        <small>{d.wd}</small>
        <strong>{d.n}</strong>
        <small>{d.mon}</small>
      </span>
      <span className="lg-main">
        <span className="lg-title">{t.title}</span>
        <span className="lg-meta">
          {s === 'blocked' && <span className="flag-block">Blocked at</span>}
          {s === 'late' && <span className="flag-late">{dueLabel(t.due_date, tz, true)} ·</span>}
          {s === 'done' ? 'All stages done' : t.current_stage_title}
        </span>
      </span>
      <span className="lg-count" aria-label={`${t.stages_done} of ${t.stages_total} stages done`}>
        {ticks ? (
          <span className="lg-ticks" aria-hidden="true">
            {Array.from({ length: t.stages_total }, (_, i) => (
              <i key={i} data-on={i < t.stages_done || undefined} />
            ))}
          </span>
        ) : (
          <span className="bar" aria-hidden="true">
            <span style={{ width: `${t.progress}%` }} />
          </span>
        )}
        <span className="lg-frac">
          {t.stages_done}/{t.stages_total}
        </span>
      </span>
    </a>
  )
}

/* 2. Hand-off: leads with where the work is right now. Task title is context; a hairline along the bottom is the progress. */
export function HandoffRow({ task: t, tz }: RowProps) {
  const s = state(t)
  return (
    <a className={`ho-row is-${s}`} href="#">
      <span className="ho-main">
        <span className="ho-task">{t.title}</span>
        <span className="ho-now">
          {s === 'done' ? (
            <>
              <Icon name="check" size={15} /> Handed over, all {t.stages_total} stages done
            </>
          ) : (
            <>
              {s === 'blocked' && <span className="dot attn" />}
              {t.current_stage_title}
              {s === 'blocked' && <span className="ho-flag">blocked</span>}
              {s === 'idle' && <span className="ho-flag quiet">not started</span>}
            </>
          )}
        </span>
      </span>
      <span className="ho-end">
        <span className={s === 'late' ? 'flag-late' : undefined}>{dueLabel(t.due_date, tz, t.is_overdue)}</span>
        <span className="ho-frac">
          {t.stages_done} of {t.stages_total}
        </span>
      </span>
      <span className="ho-line" aria-hidden="true">
        <span style={{ transform: `scaleX(${t.progress / 100})` }} />
      </span>
    </a>
  )
}

/* 3. Quiet: one line per task. State lives in a 3px rule on the left edge and in the words, nothing else. */
export function QuietRow({ task: t, tz }: RowProps) {
  const s = state(t)
  const d = new Intl.DateTimeFormat('en-US', { timeZone: tz, month: 'short', day: 'numeric' }).format(new Date(t.due_date))
  return (
    <a className={`qt-row is-${s}`} href="#">
      <span className="qt-title">{t.title}</span>
      <span className="qt-stage">
        {s === 'done' ? 'Done' : s === 'blocked' ? `Blocked: ${t.current_stage_title}` : t.current_stage_title}
      </span>
      <span className="qt-frac">
        {t.stages_done}/{t.stages_total}
      </span>
      <span className={`qt-due${s === 'late' ? ' flag-late' : ''}`} title={dueLabel(t.due_date, tz, t.is_overdue)}>
        {s === 'late' ? dueLabel(t.due_date, tz, true) : d}
      </span>
    </a>
  )
}

export const VARIANTS = [
  { name: 'Ledger', Row: LedgerRow, listClass: 'lg-list' },
  { name: 'Handoff', Row: HandoffRow, listClass: 'list ho-list' },
  { name: 'Quiet', Row: QuietRow, listClass: 'qt-list' },
]

import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { CalendarEvent } from '../lib/calendar'
import { addMonths, dayKey, monthGrid, monthLabel } from '../lib/dates'
import { Icon } from './Icon'

const STATE_LABEL = { overdue: 'Overdue', blocked: 'Blocked', done: 'Done', open: '' } as const
const MAX_CHIPS = 3

type Props = {
  month: string // "YYYY-MM"
  onMonthChange: (month: string) => void
  events: CalendarEvent[]
  timeZone: string
  loading?: boolean
  emptyText: string
}

/**
 * Month grid. Each task sits on its due day (in the viewer's profile timezone).
 * The selected day's tasks are listed below the grid, which is also the phone layout.
 */
export function MonthCalendar({ month, onMonthChange, events, timeZone, loading, emptyText }: Props) {
  const [today] = useState(() => dayKey(new Date().toISOString(), timeZone))
  const [selected, setSelected] = useState(today)
  const days = monthGrid(month)

  const byDay = new Map<string, CalendarEvent[]>()
  for (const e of events) {
    const key = dayKey(e.due, timeZone)
    byDay.set(key, [...(byDay.get(key) ?? []), e])
  }
  const selectedEvents = byDay.get(selected) ?? []
  const selectedLabel = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC' }).format(
    new Date(`${selected}T12:00:00Z`),
  )

  const go = (n: number) => onMonthChange(addMonths(month, n))

  return (
    <div className="cal">
      <div className="cal-head">
        <h2>{monthLabel(month)}</h2>
        <div className="cal-nav">
          {loading && <span className="faint small">Loading…</span>}
          <button
            className="btn sm"
            type="button"
            onClick={() => {
              onMonthChange(today.slice(0, 7))
              setSelected(today)
            }}
          >
            Today
          </button>
          <button className="icon-btn" type="button" aria-label="Previous month" onClick={() => go(-1)}>
            <Icon name="back" />
          </button>
          <button className="icon-btn" type="button" aria-label="Next month" onClick={() => go(1)}>
            <Icon name="chev" />
          </button>
        </div>
      </div>

      <div className="cal-grid" role="grid" aria-label={monthLabel(month)}>
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => (
          <div className="cal-dow" key={d} role="columnheader">
            {d}
          </div>
        ))}
        {days.map((day) => {
          const list = byDay.get(day) ?? []
          const outside = day.slice(0, 7) !== month
          const cls = ['cal-day', outside && 'outside', day === today && 'today', day === selected && 'selected']
            .filter(Boolean)
            .join(' ')
          return (
            <div className={cls} key={day} role="gridcell" aria-selected={day === selected}>
              <button
                type="button"
                className="cal-num"
                onClick={() => setSelected(day)}
                aria-label={`${day}${list.length ? `, ${list.length} due` : ''}`}
              >
                {Number(day.slice(8))}
              </button>
              <div className="cal-chips">
                {list.slice(0, MAX_CHIPS).map((e) => (
                  <Link key={e.id} to={e.href} className={`cal-chip ${e.state}`} title={[e.title, e.detail].filter(Boolean).join(' · ')}>
                    {e.title}
                  </Link>
                ))}
                {list.length > MAX_CHIPS && (
                  <button type="button" className="cal-more" onClick={() => setSelected(day)}>
                    +{list.length - MAX_CHIPS} more
                  </button>
                )}
              </div>
              {/* Phone layout: dots instead of chips */}
              {list.length > 0 && (
                <span className="cal-dots" aria-hidden="true">
                  {list.slice(0, 3).map((e) => (
                    <span key={e.id} className={`dot cal-dot ${e.state}`} />
                  ))}
                </span>
              )}
            </div>
          )
        })}
      </div>

      <section className="section">
        <div className="section-h">
          <h2>{selected === today ? `Today, ${selectedLabel.split(', ')[1]}` : selectedLabel}</h2>
        </div>
        <div className="list">
          {selectedEvents.length === 0 ? (
            <div className="empty" style={{ padding: 24 }}>
              <p>{events.length === 0 && !loading ? emptyText : 'Nothing is due this day.'}</p>
            </div>
          ) : (
            selectedEvents.map((e) => (
              <Link className="row link" to={e.href} key={e.id}>
                <span className={`dot cal-dot ${e.state}`} />
                <div className="main">
                  <div className="title">{e.title}</div>
                  {(e.detail || e.state !== 'open') && (
                    <div className="meta">
                      {e.state !== 'open' && <span className={e.state === 'overdue' ? 'flag-late' : e.state === 'blocked' ? 'flag-block' : ''}>{STATE_LABEL[e.state]}</span>}
                      {e.state !== 'open' && e.detail && <span className="sep" />}
                      {e.detail && <span>{e.detail}</span>}
                    </div>
                  )}
                </div>
                <Icon name="chev" />
              </Link>
            ))
          )}
        </div>
      </section>
    </div>
  )
}

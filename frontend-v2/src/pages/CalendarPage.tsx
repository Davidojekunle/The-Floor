import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { listTasks } from '../api/tasks'
import { CalendarSubscribe } from '../components/CalendarSubscribe'
import { Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { MonthCalendar } from '../components/MonthCalendar'
import { calendarWindow, toEvent } from '../lib/calendar'
import { dayKey } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'
import { useRoom } from '../room/roomContext'

/** Room calendar: every approved task in the room on its due day. */
export function CalendarPage() {
  const { room } = useRoom()
  const tz = useTimezone()
  const [month, setMonth] = useState(() => dayKey(new Date().toISOString(), tz).slice(0, 7))
  const [subscribing, setSubscribing] = useState(false)
  const [mineOnly, setMineOnly] = useState(false)
  const range = calendarWindow(month, tz)

  const tasks = useQuery({
    queryKey: ['tasks', room.id, 'calendar', range.from],
    queryFn: () => listTasks(room.id, range),
    placeholderData: keepPreviousData,
  })

  const events = (tasks.data?.items ?? [])
    .filter((t) => !mineOnly || t.involves_me)
    .map((t) => toEvent(t, `/rooms/${room.id}/tasks/${t.id}`))

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Calendar</h1>
          <p className="sub">Tasks in {room.name}, on the day they're due.</p>
        </div>
        <div className="cal-head-actions">
          <div className="seg" role="group" aria-label="Show">
            <button type="button" aria-pressed={!mineOnly} onClick={() => setMineOnly(false)}>
              All tasks
            </button>
            <button type="button" aria-pressed={mineOnly} onClick={() => setMineOnly(true)}>
              Involves me
            </button>
          </div>
          <button className="btn" type="button" onClick={() => setSubscribing(true)}>
            <Icon name="calendar" />
            Subscribe
          </button>
        </div>
      </div>
      {subscribing && (
        <Dialog
          title={`Subscribe to ${room.name}`}
          onClose={() => setSubscribing(false)}
          actions={
            <button className="btn ghost" type="button" onClick={() => setSubscribing(false)}>
              Done
            </button>
          }
        >
          <CalendarSubscribe roomId={room.id} roomName={room.name} />
        </Dialog>
      )}
      <MonthCalendar
        month={month}
        onMonthChange={setMonth}
        events={events}
        timeZone={tz}
        loading={tasks.isFetching}
        emptyText={mineOnly ? 'Nothing that involves you is due this month.' : 'No tasks are due this month.'}
      />
    </div>
  )
}

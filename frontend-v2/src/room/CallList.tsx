import { Link } from 'react-router-dom'
import type { Call } from '../api/calls'
import { Icon } from '../components/Icon'
import { dayAndTime } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'
import { useRoom } from './roomContext'

/** One line per call or meeting: what, when, how long, who. Shared by the Calls page and the task page. */
export function CallRow({ call: c }: { call: Call }) {
  const { room } = useRoom()
  const tz = useTimezone()
  const when = c.starts_at ?? c.started_at ?? c.ended_at
  const names = (list: { name: string }[]) =>
    list.length <= 3 ? list.map((p) => p.name).join(', ') : `${list.slice(0, 3).map((p) => p.name).join(', ')} +${list.length - 3}`

  let state: string
  let tone = ''
  if (c.status === 'live') {
    state = c.participants.length ? `Live · ${names(c.participants)}` : 'Live · nobody in yet'
    tone = 'is-live'
  } else if (c.status === 'scheduled') {
    const invited = c.invite?.everyone ? 'Everyone' : names([...(c.invite?.tags ?? []).map((t) => ({ name: t.name })), ...(c.invite?.users ?? [])])
    const going = c.rsvp?.going.length ? ` · ${c.rsvp.going.length} going` : ''
    state = `${c.duration_minutes} min · ${invited}${going}${c.repeats ? ' · repeats' : ''}`
  } else if (c.status === 'cancelled') {
    state = 'Cancelled'
    tone = 'is-off'
  } else if (c.missed) {
    state = 'Missed: nobody joined'
    tone = 'is-off'
  } else {
    state = c.attended.length ? `${c.duration_minutes ?? 0} min · ${names(c.attended)}` : 'Nobody joined'
    tone = c.attended.length ? '' : 'is-off'
  }

  return (
    <Link className={`call-row ${tone}`} to={`/rooms/${room.id}/calls/${c.id}`}>
      <span className="call-row-icon" aria-hidden="true">
        {c.status === 'live' ? <span className="live-dot" /> : <Icon name={c.kind === 'scheduled' ? 'calendar' : 'video'} size={16} />}
      </span>
      <span className="call-row-main">
        <strong>{c.title}</strong>
        <span className="faint small">
          {when ? dayAndTime(when, tz) : ''}
          {c.task ? ` · ${c.task.title}` : ''}
        </span>
      </span>
      <span className="call-row-state small">{state}</span>
    </Link>
  )
}

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listCalls } from '../api/calls'
import { Icon } from '../components/Icon'
import { CallButton } from '../room/CallButton'
import { CallRow } from '../room/CallList'
import { MeetingDialog } from '../room/MeetingDialog'
import { useCan, useRoom } from '../room/roomContext'
import { RoomBack } from '../room/RoomBack'

const PAGE = 20

/** The room's calls: live now, upcoming meetings, and the log of past calls. */
export function CallsPage() {
  const { room } = useRoom()
  const canSchedule = useCan('meeting.schedule')
  const [scheduling, setScheduling] = useState(false)
  const [pastLimit, setPastLimit] = useState(PAGE)

  const live = useQuery({ queryKey: ['calls', room.id, 'live'], queryFn: () => listCalls(room.id, { status: 'live', limit: 20 }) })
  const upcoming = useQuery({
    queryKey: ['calls', room.id, 'scheduled'],
    queryFn: () => listCalls(room.id, { status: 'scheduled', limit: 100 }),
  })
  const past = useQuery({
    queryKey: ['calls', room.id, 'past', pastLimit],
    queryFn: () => listCalls(room.id, { to: new Date().toISOString(), limit: pastLimit }),
  })

  const soonest = [...(upcoming.data?.items ?? [])].sort((a, b) => (a.starts_at ?? '').localeCompare(b.starts_at ?? ''))
  const history = (past.data?.items ?? []).filter((c) => c.status === 'ended' || c.status === 'cancelled')

  return (
    <div className="page">
      <RoomBack />
      <div className="page-head">
        <div>
          <h1>Calls</h1>
          <p className="sub">Calls and meetings in {room.name}.</p>
        </div>
        <div className="head-actions">
          <CallButton />
          {canSchedule && (
            <button className="btn primary" type="button" onClick={() => setScheduling(true)}>
              <Icon name="calendar" />
              Schedule a meeting
            </button>
          )}
        </div>
      </div>

      {(live.data?.items.length ?? 0) > 0 && (
        <section className="call-section">
          <h2>Live now</h2>
          <div className="call-list">
            {live.data!.items.map((c) => (
              <CallRow key={c.id} call={c} />
            ))}
          </div>
        </section>
      )}

      <section className="call-section">
        <h2>Upcoming</h2>
        {upcoming.isPending ? (
          <p className="empty-line">Loading…</p>
        ) : soonest.length ? (
          <div className="call-list">
            {soonest.map((c) => (
              <CallRow key={c.id} call={c} />
            ))}
          </div>
        ) : (
          <p className="empty-line">
            No meetings scheduled.{canSchedule ? ' Schedule one for the whole room, some people, or a tag.' : ''}
          </p>
        )}
      </section>

      <section className="call-section">
        <h2>Past calls</h2>
        {past.isPending ? (
          <p className="empty-line">Loading…</p>
        ) : history.length ? (
          <>
            <div className="call-list">
              {history.map((c) => (
                <CallRow key={c.id} call={c} />
              ))}
            </div>
            {(past.data?.total ?? 0) > pastLimit && (
              <button className="btn ghost sm" type="button" onClick={() => setPastLimit((n) => n + PAGE)}>
                Show more
              </button>
            )}
          </>
        ) : (
          <p className="empty-line">No calls yet. Past calls show here with how long they ran and who joined.</p>
        )}
      </section>

      {scheduling && <MeetingDialog onClose={() => setScheduling(false)} />}
    </div>
  )
}

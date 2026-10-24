import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listCalls } from '../api/calls'
import type { TaskDetail } from '../api/tasks'
import { useAuth } from '../auth/useAuth'
import { CallRow } from './CallList'
import { MeetingDialog } from './MeetingDialog'
import { useCan, useRoom } from './roomContext'

/** On a task: its meetings and past calls, and "Schedule a meeting about this task" for heads. */
export function TaskCalls({ task }: { task: TaskDetail }) {
  const { room } = useRoom()
  const { user } = useAuth()
  const canSchedule = useCan('meeting.schedule')
  const [scheduling, setScheduling] = useState(false)
  const calls = useQuery({
    queryKey: ['calls', room.id, 'task', task.id],
    queryFn: () => listCalls(room.id, { task_id: task.id, limit: 20 }),
    enabled: !!user?.calls_enabled,
  })
  if (!user?.calls_enabled) return null
  const items = calls.data?.items ?? []
  if (!items.length && !canSchedule) return null

  const upcoming = items.filter((c) => c.status === 'scheduled' || c.status === 'live')
    .sort((a, b) => (a.starts_at ?? a.started_at ?? '').localeCompare(b.starts_at ?? b.started_at ?? ''))
  const past = items.filter((c) => c.status === 'ended')
  return (
    <section className="section">
      <div className="section-head">
        <h2>Meetings and calls</h2>
        {canSchedule && (
          <button className="btn ghost sm" type="button" onClick={() => setScheduling(true)}>
            Schedule a meeting about this task
          </button>
        )}
      </div>
      {items.length ? (
        <div className="call-list">
          {[...upcoming, ...past].map((c) => (
            <CallRow key={c.id} call={c} />
          ))}
        </div>
      ) : (
        <p className="empty-line">No meetings about this task yet.</p>
      )}
      {scheduling && <MeetingDialog task={{ id: task.id, title: task.title }} onClose={() => setScheduling(false)} />}
    </section>
  )
}

import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listTasks } from '../api/tasks'
import { ProgressBar } from '../components/ProgressBar'
import { formatDateTime } from '../lib/format'
import { useRoom } from '../room/useRoom'

export function RoomHomePage() {
  const { room } = useRoom()

  const tasks = useQuery({
    queryKey: ['tasks', room.id, 'list'],
    queryFn: () => listTasks(room.id, { limit: 50 }),
    refetchInterval: 45_000,
  })

  let list
  if (tasks.isPending) {
    list = <p>Loading tasks...</p>
  } else if (tasks.isError) {
    list = <p>Could not load tasks.</p>
  } else if (tasks.data.items.length === 0) {
    list = <p>No tasks yet.</p>
  } else {
    list = tasks.data.items.map((t) => (
      <div className="task-card" key={t.id}>
        <div className="task-card-top">
          <Link to={`/rooms/${room.id}/tasks/${t.id}`}>
            <strong>{t.title}</strong>
          </Link>
          <span>
            {t.involves_me && <span className="badge mine">Yours</span>}
            {t.status === 'done' && <span className="badge done">Done</span>}
            {t.is_blocked && <span className="badge blocked">Blocked</span>}
            {t.is_overdue && <span className="badge overdue">Overdue</span>}
          </span>
        </div>
        <ProgressBar value={t.progress} />
        <div className="muted">
          {t.stages_done} of {t.stages_total} stages
          {t.current_stage_title ? ` · now: ${t.current_stage_title}` : ''} ·
          due {formatDateTime(t.due_date)}
        </div>
      </div>
    ))
  }

  return (
    <div>
      {room.temp_head_expires_at && (
        <div className="banner">
          You have temporary head access until{' '}
          {new Date(room.temp_head_expires_at).toLocaleDateString()}.
        </div>
      )}
      <h1>{room.name}</h1>
      <p className="muted">{room.member_count} members</p>

      <h2>Tasks</h2>
      {list}
    </div>
  )
}
import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listMyTasks, type MyStage, type MyTask } from '../api/me'
import { MonthCalendar } from '../components/MonthCalendar'
import { calendarWindow, toEvent } from '../lib/calendar'
import { dayKey, dueLabel } from '../lib/dates'
import { plural } from '../lib/labels'
import { useTimezone } from '../lib/useTimezone'
import { ProposalRow } from '../room/ProposalRow'
import { StageActions } from '../room/StageActions'

type View = 'list' | 'calendar'
type Item = { task: MyTask; stage: MyStage }

const URGENCY: Record<string, number> = { blocked: 0, in_progress: 1, todo: 2, locked: 3 }

/** My stages across every room I'm in, plus a calendar of my work (or everything). */
export function MyWorkPage() {
  const [view, setView] = useState<View>('list')

  return (
    <>
      <div className="container">
        <div className="page">
          <div className="page-head">
            <div>
              <h1>My work</h1>
              <p className="sub">Your stages across all your rooms.</p>
            </div>
            <div className="seg" role="group" aria-label="View">
              <button type="button" aria-pressed={view === 'list'} onClick={() => setView('list')}>
                List
              </button>
              <button type="button" aria-pressed={view === 'calendar'} onClick={() => setView('calendar')}>
                Calendar
              </button>
            </div>
          </div>
          {view === 'list' ? (
            <>
              <MyWorkList />
              <MyProposals />
            </>
          ) : (
            <MyCalendar />
          )}
        </div>
      </div>
    </>
  )
}

function MyWorkList() {
  const tz = useTimezone()
  const query = useQuery({ queryKey: ['me-tasks', { scope: 'mine' }], queryFn: () => listMyTasks() })

  if (query.isPending) return <div className="empty"><p>Loading your work…</p></div>
  if (query.isError)
    return (
      <div className="empty">
        <p>Your work didn't load.</p>
        <button className="btn sm" type="button" onClick={() => void query.refetch()}>
          Try again
        </button>
      </div>
    )

  const items: Item[] = query.data.items.flatMap((task) =>
    task.my_stages.filter((s) => s.status !== 'done').map((stage) => ({ task, stage })),
  )
  // Most urgent first: blocked, then overdue, then by due date.
  const due = (i: Item) => i.stage.due_date ?? i.task.due_date
  const byUrgency = (a: Item, b: Item) =>
    (URGENCY[a.stage.status] ?? 9) - (URGENCY[b.stage.status] ?? 9) ||
    Number(b.stage.is_overdue || b.task.is_overdue) - Number(a.stage.is_overdue || a.task.is_overdue) ||
    due(a).localeCompare(due(b))

  const now = items.filter((i) => i.stage.status !== 'locked').sort(byUrgency)
  const later = items.filter((i) => i.stage.status === 'locked').sort(byUrgency)

  if (!items.length)
    return (
      <div className="list">
        <div className="empty">
          <h2>Nothing needs you right now</h2>
          <p>Stages assigned to you, or to a tag you hold, show up here.</p>
          <Link className="btn" to="/rooms" style={{ marginTop: 8 }}>
            Go to your rooms
          </Link>
        </div>
      </div>
    )

  return (
    <>
      <section className="section">
        <div className="section-h">
          <h2>Ready for you</h2>
          <span className="faint small">{plural(now.length, 'stage')}</span>
        </div>
        <div className="list">
          {now.length ? (
            now.map((i) => <WorkRow key={i.stage.id} item={i} tz={tz} />)
          ) : (
            <div className="empty" style={{ padding: 24 }}>
              <p>Nothing is ready yet. Your next stages are waiting on others.</p>
            </div>
          )}
        </div>
      </section>
      {later.length > 0 && (
        <section className="section">
          <div className="section-h">
            <h2>Coming up</h2>
            <span className="faint small">Waiting on earlier stages</span>
          </div>
          <div className="list">
            {later.map((i) => (
              <WorkRow key={i.stage.id} item={i} tz={tz} />
            ))}
          </div>
        </section>
      )}
    </>
  )
}

function WorkRow({ item: { task, stage }, tz }: { item: Item; tz: string }) {
  const href = `/rooms/${task.room.id}/tasks/${task.id}`
  const dueIso = stage.due_date ?? task.due_date
  const late = stage.due_date ? stage.is_overdue : task.is_overdue
  return (
    <div className="row">
      <span className={`dot status-${stage.status}`} />
      <div className="main">
        <div className="title">{stage.title}</div>
        <div className="meta">
          <Link className="meta-link" to={href}>
            {task.title}
          </Link>
          <span className="sep" />
          <span>{task.room.name}</span>
          {!stage.assigned_to_me && stage.tag && <span className="tag">via {stage.tag.name}</span>}
          <span className="sep" />
          <span className={late ? 'flag-late' : undefined}>{dueLabel(dueIso, tz, late)}</span>
          {stage.status === 'blocked' && (
            <>
              <span className="sep" />
              <span className="flag-block">Blocked{stage.blocked_reason ? `: ${stage.blocked_reason}` : ''}</span>
            </>
          )}
        </div>
      </div>
      <div className="end wrap-ok">
        {stage.status === 'locked' && stage.allowed_statuses.length === 0 ? (
          <span className="faint small">Waiting on {task.current_stage_title ?? 'the previous stage'}</span>
        ) : (
          <StageActions roomId={task.room.id} taskId={task.id} stage={stage} />
        )}
      </div>
    </div>
  )
}

/** My own pending and rejected proposals, across every room. Hidden when there are none. */
function MyProposals() {
  const query = useQuery({
    queryKey: ['me-tasks', { proposals: true }],
    queryFn: () => listMyTasks({ approval_status: 'pending,rejected', sort: 'submitted_at' }),
  })
  const items = query.data?.items ?? []
  if (!items.length) return null
  return (
    <section className="section">
      <div className="section-h">
        <h2>Your proposals</h2>
        <span className="faint small">Waiting for a head, or sent back to you</span>
      </div>
      <div className="list">
        {items.map((t) => (
          <ProposalRow key={t.id} task={t} mode="mine" roomName={t.room.name} href={`/rooms/${t.room.id}/tasks/${t.id}`} />
        ))}
      </div>
    </section>
  )
}

function MyCalendar() {
  const tz = useTimezone()
  const [month, setMonth] = useState(() => dayKey(new Date().toISOString(), tz).slice(0, 7))
  const [scope, setScope] = useState<'mine' | 'all'>('mine')
  const range = calendarWindow(month, tz)

  const query = useQuery({
    queryKey: ['me-tasks', { scope, from: range.from }],
    queryFn: () => listMyTasks({ scope, ...range }),
    placeholderData: keepPreviousData,
  })

  const events = (query.data?.items ?? []).map((t) => toEvent(t, `/rooms/${t.room.id}/tasks/${t.id}`, t.room.name))

  return (
    <div className="section" style={{ gap: 16 }}>
      <div className="seg" role="group" aria-label="Whose tasks" style={{ justifySelf: 'start' }}>
        <button type="button" aria-pressed={scope === 'mine'} onClick={() => setScope('mine')}>
          My tasks
        </button>
        <button type="button" aria-pressed={scope === 'all'} onClick={() => setScope('all')}>
          Everything in my rooms
        </button>
      </div>
      <MonthCalendar
        month={month}
        onMonthChange={setMonth}
        events={events}
        timeZone={tz}
        loading={query.isFetching}
        emptyText={scope === 'mine' ? 'None of your tasks are due this month.' : 'No tasks are due this month.'}
      />
    </div>
  )
}

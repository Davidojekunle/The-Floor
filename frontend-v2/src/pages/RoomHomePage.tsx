import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listMessages } from '../api/chat'
import { listTasks, type TaskListItem } from '../api/tasks'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { addDays, dayInput, dayKey, dueLabel, formatDay, relativeTime } from '../lib/dates'
import { plural } from '../lib/labels'
import { useTimezone } from '../lib/useTimezone'
import { ProposalRow } from '../room/ProposalRow'
import { useCan, useRoom } from '../room/roomContext'
import { StageActions } from '../room/StageActions'
import { useMyStages, type MyStageItem } from '../room/useMyStages'

type Filter = 'all' | 'mine'
type Group = 'overdue' | 'week' | 'later' | 'done'
const GROUPS: { key: Group; label: string }[] = [
  { key: 'overdue', label: 'Overdue' },
  { key: 'week', label: 'This week' },
  { key: 'later', label: 'Later' },
  { key: 'done', label: 'Done' },
]

/**
 * A room's home (layout v3). Tasks on the left, grouped by urgency. On the right, what needs *you*:
 * attention (heads), your next steps, your proposals, then what's coming up and recent activity.
 * Under 1180px the "you" cards move above the tasks; on phones the last two are left out
 * (the groups and the Chat tab already cover them).
 */
export function RoomHomePage() {
  const { room } = useRoom()
  const { user } = useAuth()
  const tz = useTimezone()
  const [today] = useState(() => dayInput(tz))
  const canCreate = useCan('task.create')
  const canManageJoins = useCan('join.manage')
  const canApprove = useCan('task.approve')
  const canPropose = useCan('task.propose')
  const [filter, setFilter] = useState<Filter>('all')
  const [showDone, setShowDone] = useState(false)

  const all = useQuery({ queryKey: ['tasks', room.id, 'all'], queryFn: () => listTasks(room.id) })
  const mineList = useQuery({
    queryKey: ['tasks', room.id, 'mine'],
    queryFn: () => listTasks(room.id, { assignee: 'me' }),
    enabled: filter === 'mine',
  })
  const list = filter === 'all' ? all : mineList
  const mine = useMyStages(room.id)
  const isMember = !canCreate

  const proposals = useQuery({
    queryKey: ['tasks', room.id, 'proposals', 'mine'],
    queryFn: () => listTasks(room.id, { approval_status: 'pending,rejected', sort: 'submitted_at' }),
    enabled: isMember && canPropose,
  })
  const myProposals = (proposals.data?.items ?? []).filter((t) => t.created_by.id === user?.id)

  const summary = user?.rooms.find((r) => r.id === room.id)
  const joins = canManageJoins ? (summary?.pending_join_requests ?? 0) : 0
  const proposed = canApprove ? (summary?.pending_proposals ?? 0) : 0
  const tasks = all.data?.items ?? []
  const attention = canCreate ? tasks.filter((t) => t.status !== 'done' && (t.is_blocked || t.is_overdue)) : []
  const nextSteps = mine.stages.filter((m) => m.stage.status !== 'locked' || m.stage.allowed_statuses.length > 0)

  const weekEnd = addDays(today, 6)
  const groupOf = (t: TaskListItem): Group =>
    t.status === 'done' ? 'done' : t.is_overdue ? 'overdue' : dayKey(t.due_date, tz) <= weekEnd ? 'week' : 'later'
  const grouped = new Map<Group, TaskListItem[]>(GROUPS.map((g) => [g.key, []]))
  for (const t of [...(list.data?.items ?? [])].sort((a, b) => a.due_date.localeCompare(b.due_date))) grouped.get(groupOf(t))!.push(t)

  const sub = room.temp_head_expires_at
    ? `You're a temporary head until ${formatDay(room.temp_head_expires_at, tz)}`
    : plural(room.member_count, 'member')

  const attentionCard = (joins > 0 || proposed > 0 || attention.length > 0) && (
    <Card title="Needs your attention">
      {joins > 0 && (
        <Link className="row link" to={`/rooms/${room.id}/requests`}>
          <span className="dot attn" />
          <div className="main">
            <div className="title">{joins === 1 ? '1 person wants to join' : `${joins} people want to join`}</div>
          </div>
          <Icon name="chev" />
        </Link>
      )}
      {proposed > 0 && (
        <Link className="row link" to={`/rooms/${room.id}/requests`}>
          <span className="dot attn" />
          <div className="main">
            <div className="title">{proposed === 1 ? '1 task was proposed' : `${proposed} tasks were proposed`}</div>
            <div className="meta">Approve or reject</div>
          </div>
          <Icon name="chev" />
        </Link>
      )}
      {attention.map((t) => (
        <Link className="row link" key={t.id} to={`/rooms/${room.id}/tasks/${t.id}`}>
          <span className={`dot ${t.is_blocked ? 'attn' : 'danger'}`} />
          <div className="main">
            <div className="title">{t.title}</div>
            <div className="meta">
              {t.is_blocked ? <span className="flag-block">Blocked</span> : <span className="flag-late">{dueLabel(t.due_date, tz, true)}</span>}
              {t.current_stage_title && <span> · {t.current_stage_title}</span>}
            </div>
          </div>
          <Icon name="chev" />
        </Link>
      ))}
    </Card>
  )

  const nextCard = nextSteps.length > 0 && (
    <Card
      title="Your next steps"
      action={
        <Link className="link-btn" to="/my-work">
          All your work
        </Link>
      }
    >
      {nextSteps.slice(0, 5).map((m) => (
        <NextStep key={m.stage.id} item={m} />
      ))}
    </Card>
  )

  const proposalsCard = myProposals.length > 0 && (
    <Card title="Your proposals">
      {myProposals.map((t) => (
        <ProposalRow key={t.id} task={t} mode="mine" href={`/rooms/${room.id}/tasks/${t.id}`} />
      ))}
    </Card>
  )

  return (
    <div className="page home">
      <div className="page-head">
        <div>
          <h1>{room.name}</h1>
          <p className="sub">{sub}</p>
        </div>
        {(canCreate || canPropose) && (
          <Link className={`btn${canCreate ? ' primary' : ''}`} to={`/rooms/${room.id}/tasks/new`}>
            <Icon name="plus" />
            {canCreate ? 'New task' : 'Propose a task'}
          </Link>
        )}
      </div>

      <div className="home-grid">
        <div className="rail rail-top">
          {attentionCard}
          {nextCard}
          {proposalsCard}
        </div>

        <section className="section home-tasks" aria-label="Tasks">
          <div className="section-h">
            <h2>{isMember ? 'All tasks in this room' : 'Tasks'}</h2>
            <div className="seg" role="group" aria-label="Filter tasks">
              <button type="button" aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>
                All
              </button>
              <button type="button" aria-pressed={filter === 'mine'} onClick={() => setFilter('mine')}>
                Involves me
              </button>
            </div>
          </div>

          {list.isPending ? (
            <div className="list">
              <div className="empty">
                <p>Loading tasks…</p>
              </div>
            </div>
          ) : list.isError ? (
            <div className="list">
              <div className="empty">
                <p>Tasks didn't load.</p>
                <button className="btn sm" type="button" onClick={() => void list.refetch()}>
                  Try again
                </button>
              </div>
            </div>
          ) : list.data.items.length === 0 ? (
            <div className="list">
              <EmptyTasks filter={filter} canCreate={canCreate} roomId={room.id} />
            </div>
          ) : (
            GROUPS.map(({ key, label }) => {
              const items = grouped.get(key)!
              if (!items.length) return null
              const collapsed = key === 'done' && !showDone
              return (
                <div className="task-group" key={key}>
                  {key === 'done' ? (
                    <button type="button" className="grp grp-btn" aria-expanded={showDone} onClick={() => setShowDone(!showDone)}>
                      <Icon name={showDone ? 'down' : 'chev'} size={14} />
                      {label} <span className="n">{items.length}</span>
                    </button>
                  ) : (
                    <h3 className={`grp ${key}`}>
                      {label} <span className="n">{items.length}</span>
                    </h3>
                  )}
                  {!collapsed && (
                    <div className="list">
                      {items.map((t) => (
                        <TaskRow key={t.id} task={t} roomId={room.id} tz={tz} />
                      ))}
                    </div>
                  )}
                </div>
              )
            })
          )}
        </section>

        <div className="rail rail-bottom">
          <ComingUp tasks={tasks} stages={mine.stages} today={today} weekEnd={weekEnd} loading={all.isPending || mine.isPending} />
          <RecentActivity />
        </div>
      </div>
    </div>
  )
}

function Card({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="rail-card" aria-label={title}>
      <h3>
        {title}
        {action}
      </h3>
      <div className="rail-rows">{children}</div>
    </section>
  )
}

function TaskRow({ task: t, roomId, tz }: { task: TaskListItem; roomId: string; tz: string }) {
  const done = t.status === 'done'
  return (
    <Link className="row link" to={`/rooms/${roomId}/tasks/${t.id}`}>
      <div className="main">
        <div className="title">{t.title}</div>
        <div className="meta">
          {t.is_blocked && (
            <span className="flag-block">
              <span className="dot attn" />
              Blocked
            </span>
          )}
          <span>{done ? 'All stages done' : `Now: ${t.current_stage_title ?? '—'}`}</span>
          <span className="sep" />
          <span className={t.is_overdue ? 'flag-late' : undefined}>{dueLabel(t.due_date, tz, t.is_overdue)}</span>
        </div>
      </div>
      <div className="progress hide-sm" aria-label={`${t.stages_done} of ${t.stages_total} stages done`}>
        <div className={`bar ${done ? 'done' : ''}`}>
          <span style={{ width: `${t.progress}%` }} />
        </div>
        {t.stages_done}/{t.stages_total}
      </div>
      <Icon name="chev" />
    </Link>
  )
}

function NextStep({ item: { task, stage } }: { item: MyStageItem }) {
  const { room } = useRoom()
  const tz = useTimezone()
  return (
    <div className="row next-step">
      <span className={`dot status-${stage.status}`} />
      <div className="main">
        <div className="title">{stage.title}</div>
        <div className="meta">
          <Link className="meta-link" to={`/rooms/${room.id}/tasks/${task.id}`}>
            {task.title}
          </Link>
          {stage.due_date && (
            <>
              <span className="sep" />
              <span className={stage.is_overdue ? 'flag-late' : undefined}>{dueLabel(stage.due_date, tz, stage.is_overdue)}</span>
            </>
          )}
          {stage.status === 'blocked' && (
            <>
              <span className="sep" />
              <span className="flag-block" title={stage.blocked_reason ?? undefined}>
                Blocked
              </span>
            </>
          )}
        </div>
      </div>
      <div className="end wrap-ok">
        <StageActions roomId={room.id} taskId={task.id} stage={stage} />
      </div>
    </div>
  )
}

/** The next seven days as a short timeline: task deadlines and my stage deadlines. */
function ComingUp(props: { tasks: TaskListItem[]; stages: MyStageItem[]; today: string; weekEnd: string; loading: boolean }) {
  const { room } = useRoom()
  const tz = useTimezone()
  const inWeek = (iso: string) => {
    const d = dayKey(iso, tz)
    return d >= props.today && d <= props.weekEnd
  }
  const entries = [
    ...props.tasks.filter((t) => t.status !== 'done' && !t.is_overdue && inWeek(t.due_date)).map((t) => ({
      id: t.id,
      when: t.due_date,
      title: t.title,
      meta: 'Task due',
      href: `/rooms/${room.id}/tasks/${t.id}`,
    })),
    ...props.stages
      .filter((m) => m.stage.due_date && !m.stage.is_overdue && inWeek(m.stage.due_date))
      .map((m) => ({
        id: m.stage.id,
        when: m.stage.due_date!,
        title: m.stage.title,
        meta: `Your stage · ${m.task.title}`,
        href: `/rooms/${room.id}/tasks/${m.task.id}`,
      })),
  ].sort((a, b) => a.when.localeCompare(b.when))

  const day = (iso: string) => {
    const d = new Date(iso)
    return {
      wd: new Intl.DateTimeFormat('en-US', { timeZone: tz, weekday: 'short' }).format(d),
      n: new Intl.DateTimeFormat('en-US', { timeZone: tz, day: 'numeric' }).format(d),
    }
  }

  return (
    <Card title="Coming up">
      {props.loading ? (
        <p className="empty-line">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="empty-line">Nothing due in the next seven days.</p>
      ) : (
        <div className="tl">
          {entries.slice(0, 6).map((e) => {
            const d = day(e.when)
            return (
              <Link className="tl-row" key={e.id} to={e.href}>
                <span className="tl-day">
                  <small>{d.wd}</small>
                  <strong>{d.n}</strong>
                </span>
                <span className="tl-text">
                  <span className="title">{e.title}</span>
                  <span className="meta">{e.meta}</span>
                </span>
              </Link>
            )
          })}
        </div>
      )}
    </Card>
  )
}

/** The room's latest automatic chat lines ("Ada finished Script"). */
function RecentActivity() {
  const { room } = useRoom()
  const tz = useTimezone()
  const q = useQuery({ queryKey: ['activity', room.id], queryFn: () => listMessages(room.id, { limit: 30 }) })
  const lines = (q.data?.items ?? []).filter((m) => m.type === 'system' && m.body).slice(0, 5)
  return (
    <Card
      title="Recent activity"
      action={
        <Link className="link-btn" to={`/rooms/${room.id}/chat`}>
          Open chat
        </Link>
      }
    >
      {q.isPending ? (
        <p className="empty-line">Loading…</p>
      ) : lines.length === 0 ? (
        <p className="empty-line">Nothing yet. Stage changes and new members show up here.</p>
      ) : (
        lines.map((m) => (
          <div className="act" key={m.id}>
            <span className="ico">
              <Icon name="bolt" size={12} />
            </span>
            <span>
              {m.body}
              <time dateTime={m.created_at}>{relativeTime(m.created_at, tz)}</time>
            </span>
          </div>
        ))
      )}
    </Card>
  )
}

function EmptyTasks({ filter, canCreate, roomId }: { filter: Filter; canCreate: boolean; roomId: string }) {
  if (filter === 'mine')
    return (
      <div className="empty">
        <p>No tasks involve you yet.</p>
      </div>
    )
  return (
    <div className="empty">
      <h2>No tasks yet</h2>
      <p>{canCreate ? 'Create the first one, or start from a template.' : 'Tasks the head creates will show up here.'}</p>
      {canCreate && (
        <Link className="btn" to={`/rooms/${roomId}/tasks/new`} style={{ marginTop: 8 }}>
          New task
        </Link>
      )}
    </div>
  )
}

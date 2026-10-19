import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate } from 'react-router-dom'
import { getAdminStats, type AdminStats } from '../api/admin'
import { useAuth } from '../auth/useAuth'
import { relativeTime } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'

type Tone = 'ok' | 'attn' | 'bad'
type Metric = 'signups' | 'tasks_created' | 'stages_done' | 'messages'

const METRICS: { key: Metric; label: string }[] = [
  { key: 'signups', label: 'Sign-ups' },
  { key: 'tasks_created', label: 'Tasks made' },
  { key: 'stages_done', label: 'Stages done' },
  { key: 'messages', label: 'Messages' },
]

/** Staff only: is the app healthy, and is it being used? Counts only, never anyone's content. */
export function AdminPage() {
  const { user } = useAuth()
  const stats = useQuery({
    queryKey: ['admin-stats'],
    queryFn: getAdminStats,
    enabled: !!user?.is_staff,
    refetchInterval: 30_000,
  })

  if (user && !user.is_staff) return <Navigate to="/rooms" replace />

  return (
    <div className="container">
      <div className="page">
        <div className="page-head">
          <div>
            <h1>Admin</h1>
            <p className="sub">Health and usage across The Floor. Totals only: no names, tasks or messages.</p>
          </div>
          <button className="btn" type="button" disabled={stats.isFetching} onClick={() => void stats.refetch()}>
            {stats.isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
        {stats.isPending ? (
          <div className="empty">
            <p>Loading the numbers…</p>
          </div>
        ) : stats.isError ? (
          <div className="empty">
            <p>The numbers didn't load. Refresh to try again.</p>
          </div>
        ) : (
          <AdminBody s={stats.data} />
        )}
      </div>
    </div>
  )
}

function AdminBody({ s }: { s: AdminStats }) {
  const tz = useTimezone()
  const h = s.health
  const now = new Date(s.generated_at).getTime() // the server's clock, when it counted
  const loopAge = h.loop_last_run_at ? (now - new Date(h.loop_last_run_at).getTime()) / 1000 : null
  const loopTone: Tone = loopAge === null ? (h.uptime_seconds > 120 ? 'bad' : 'attn') : loopAge > 120 ? 'bad' : 'ok'
  const emailAge = h.oldest_waiting_email_at ? (now - new Date(h.oldest_waiting_email_at).getTime()) / 1000 : 0
  const answered = s.activity.nudges_30d ? Math.round((s.activity.nudges_answered_30d / s.activity.nudges_30d) * 100) : null

  return (
    <>
      <section className="admin-sec" aria-labelledby="adm-health">
        <h2 id="adm-health">Health</h2>
        <div className="admin-health">
          <HealthRow tone={h.database_ok ? 'ok' : 'bad'} label="Database">
            {h.database_ok ? `Connected · ${h.database_ms} ms` : 'Not answering'}
          </HealthRow>
          <HealthRow tone={loopTone} label="Background jobs" hint="Sends emails and reminders every few seconds.">
            {h.loop_last_run_at ? `Last ran ${relativeTime(h.loop_last_run_at, tz)}` : 'Hasn’t run since the restart'}
            {h.loop_last_error_at && (
              <span className="faint"> · last error {relativeTime(h.loop_last_error_at, tz)} ({h.loop_last_error})</span>
            )}
          </HealthRow>
          <HealthRow tone={h.emails_waiting === 0 || emailAge < 300 ? 'ok' : 'attn'} label="Email queue">
            {h.emails_waiting === 0 ? 'Empty' : `${h.emails_waiting} waiting, oldest ${relativeTime(h.oldest_waiting_email_at!, tz)}`}
          </HealthRow>
          <HealthRow tone={h.emails_failed_7d ? 'attn' : 'ok'} label="Emails, last 7 days">
            {h.emails_sent_7d} sent · {h.emails_failed_7d} failed
          </HealthRow>
          <HealthRow tone={h.push_failed_since_start ? 'attn' : 'ok'} label="Push since restart">
            {h.push_sent_since_start} sent · {h.push_failed_since_start} failed · {h.push_expired_since_start} expired
          </HealthRow>
          <HealthRow label="Running">
            Up {uptime(h.uptime_seconds)} · database version {h.migration ?? 'unknown'}
          </HealthRow>
        </div>
      </section>

      <section className="admin-sec" aria-labelledby="adm-people">
        <h2 id="adm-people">People and rooms</h2>
        <div className="admin-stats">
          <Stat value={s.people.total} label="Accounts" note={`${s.people.new_7d} new this week`} />
          <Stat value={s.people.active_7d} label="Active this week" note={`${s.people.active_30d} in 30 days`} />
          <Stat value={s.rooms.total} label="Rooms" note={`${s.rooms.active_30d} active in 30 days`} />
          <Stat value={s.rooms.average_members} label="Members per room" note="on average" />
          <Stat value={s.people.with_push} label="Push on" note="people with it on a device" />
          <Stat value={s.people.with_calendar} label="Calendar links" note="people who made one" />
        </div>
      </section>

      <section className="admin-sec" aria-labelledby="adm-work">
        <h2 id="adm-work">Work</h2>
        <div className="admin-stats">
          <Stat value={s.work.tasks_open} label="Open tasks" note={`of ${s.work.tasks_total}`} />
          <Stat value={s.work.tasks_finished_7d} label="Finished this week" note={`${s.work.tasks_created_7d} made this week`} />
          <Stat value={s.work.stages_done_7d} label="Stages done this week" note={`${s.work.stages_in_progress} in progress now`} />
          <Stat value={s.work.stages_overdue} label="Overdue stages" tone={s.work.stages_overdue ? 'bad' : undefined} />
          <Stat value={s.work.stages_blocked} label="Blocked stages" tone={s.work.stages_blocked ? 'attn' : undefined} />
          <Stat value={s.work.stages_stuck} label="Stuck 3+ days" note="To do or In progress" />
          <Stat value={s.work.proposals_waiting} label="Proposals waiting" />
          <Stat value={s.rooms.pending_join_requests} label="Join requests waiting" />
        </div>
      </section>

      <section className="admin-sec" aria-labelledby="adm-activity">
        <h2 id="adm-activity">Activity</h2>
        <div className="admin-stats">
          <Stat value={s.activity.messages_7d} label="Chat messages" note="this week" />
          <Stat value={s.activity.updates_7d} label="Progress updates" note="this week" />
          <Stat value={s.activity.nudges_30d} label="Nudges" note="in 30 days" />
          <Stat value={answered === null ? '–' : `${answered}%`} label="Nudges answered" note="in 30 days" />
        </div>
      </section>

      <Weeks s={s} />
      <p className="faint small">Updated {relativeTime(s.generated_at, tz)}. Refreshes every 30 seconds.</p>
    </>
  )
}

function HealthRow(props: { tone?: Tone; label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="admin-hrow">
      <span className={`admin-dot${props.tone ? ` ${props.tone}` : ''}`} aria-hidden="true" />
      <div className="admin-hlabel">
        {props.label}
        {props.hint && <div className="faint small">{props.hint}</div>}
      </div>
      <div className="admin-hval">
        {props.tone && <span className="sr-only">{props.tone === 'ok' ? 'OK: ' : props.tone === 'attn' ? 'Check: ' : 'Problem: '}</span>}
        {props.children}
      </div>
    </div>
  )
}

function Stat(props: { value: number | string; label: string; note?: string; tone?: 'attn' | 'bad' }) {
  return (
    <div className="admin-stat">
      <div className={`admin-num${props.tone ? ` ${props.tone}` : ''}`}>{props.value}</div>
      <div className="admin-label">{props.label}</div>
      {props.note && <div className="faint small">{props.note}</div>}
    </div>
  )
}

function Weeks({ s }: { s: AdminStats }) {
  const tz = useTimezone()
  const [metric, setMetric] = useState<Metric>('signups')
  const max = Math.max(1, ...s.weeks.map((w) => w[metric]))
  return (
    <section className="admin-sec" aria-labelledby="adm-weeks">
      <div className="admin-sec-head">
        <h2 id="adm-weeks">Last 8 weeks</h2>
        <div className="seg" role="group" aria-label="Show">
          {METRICS.map((m) => (
            <button key={m.key} type="button" aria-pressed={metric === m.key} onClick={() => setMetric(m.key)}>
              {m.label}
            </button>
          ))}
        </div>
      </div>
      <ol className="admin-bars">
        {s.weeks.map((w, i) => (
          <li key={w.week_start}>
            <span className="admin-bar-n">{w[metric]}</span>
            <span className="admin-bar" style={{ height: `${(w[metric] / max) * 100}%` }} />
            <span className="admin-bar-d">{weekLabel(w.week_start, i === 0 ? null : s.weeks[i - 1].week_start, tz)}</span>
          </li>
        ))}
      </ol>
      <p className="faint small">Each bar is a week, starting on the day shown.</p>
    </section>
  )
}

/** "Aug 24", then just "31" until the month changes ("Sep 7"), so eight labels fit on a phone. */
function weekLabel(iso: string, prevIso: string | null, timeZone: string) {
  const month = (d: string) => new Intl.DateTimeFormat('en-US', { timeZone, month: 'short' }).format(new Date(d))
  const day = new Intl.DateTimeFormat('en-US', { timeZone, day: 'numeric' }).format(new Date(iso))
  return prevIso && month(prevIso) === month(iso) ? day : `${month(iso)} ${day}`
}

function uptime(seconds: number) {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d) return `${d}d ${h}h`
  if (h) return `${h}h ${m}m`
  return `${m}m`
}

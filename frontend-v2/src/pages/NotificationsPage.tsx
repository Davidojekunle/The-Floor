import { useState } from 'react'
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  listNotifications,
  markNotificationRead,
  markNotificationsRead,
  type Notification,
  type NotificationPage,
} from '../api/notifications'
import { useAuth } from '../auth/useAuth'
import { Icon, type IconName } from '../components/Icon'
import { useToast } from '../components/toastContext'
import { formatDay, relativeTime } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'

const ICON: Record<string, IconName> = {
  join_requested: 'users',
  join_approved: 'users',
  proposal_submitted: 'inbox',
  proposal_approved: 'check',
  proposal_rejected: 'x',
  stages_unassigned: 'layers',
  temp_head_granted: 'bolt',
  head_transferred: 'bolt',
  removed_from_room: 'x',
  room_deleted: 'x',
  stage_ready: 'task',
  stage_assigned: 'task',
}

/** Where tapping a notification goes. Null when the place is gone (a deleted room, a room you were removed from). */
function targetOf(n: Notification): string | null {
  if (!n.room || n.type === 'room_deleted' || n.type === 'removed_from_room') return null
  const room = `/rooms/${n.room.id}`
  if (n.type === 'join_requested' || n.type === 'proposal_submitted') return `${room}/requests`
  if (n.type === 'stages_unassigned') {
    const first = n.data?.stages?.[0]
    return first ? `${room}/tasks/${first.task_id}` : room
  }
  if (n.task) return `${room}/tasks/${n.task.id}`
  return room
}

/** The bell (L4): everything that happened for you, newest first. Opening an item marks it read. */
export function NotificationsPage() {
  const { user, refreshUser } = useAuth()
  const queryClient = useQueryClient()
  const toast = useToast()
  const [unreadOnly, setUnreadOnly] = useState(false)
  const unread = user?.unread_notifications ?? 0

  const q = useInfiniteQuery({
    queryKey: ['notifications', { unreadOnly }],
    queryFn: ({ pageParam }) => listNotifications({ unread: unreadOnly, before: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: NotificationPage) => (last.has_more ? last.items.at(-1)?.id : undefined),
  })
  const items = q.data?.pages.flatMap((p) => p.items) ?? []

  const markAll = useMutation({
    mutationFn: () => markNotificationsRead(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] })
      void refreshUser()
      toast('All caught up.')
    },
    onError: (err) => toast(err instanceof Error ? err.message : 'Something went wrong.'),
  })

  return (
    <div className="container">
    <div className="page narrow notifications">
      <div className="page-head">
        <div>
          <h1>Notifications</h1>
          <p className="sub">{unread ? `${unread} unread` : "You're all caught up."}</p>
        </div>
        {unread > 0 && (
          <button className="btn" type="button" disabled={markAll.isPending} onClick={() => markAll.mutate()}>
            <Icon name="check" />
            Mark all as read
          </button>
        )}
      </div>

      <div className="seg" role="group" aria-label="Show">
        <button type="button" aria-pressed={!unreadOnly} onClick={() => setUnreadOnly(false)}>
          All
        </button>
        <button type="button" aria-pressed={unreadOnly} onClick={() => setUnreadOnly(true)}>
          Unread{unread ? ` · ${unread}` : ''}
        </button>
      </div>

      <div className="list notif-list">
        {q.isPending ? (
          <div className="empty">
            <p>Loading…</p>
          </div>
        ) : q.isError ? (
          <div className="empty">
            <p>Notifications didn't load.</p>
            <button className="btn sm" type="button" onClick={() => void q.refetch()}>
              Try again
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="empty">
            <span className="notif-empty-ico" aria-hidden="true">
              <Icon name="bell" size={22} />
            </span>
            <h2>{unreadOnly ? 'Nothing unread' : 'No notifications yet'}</h2>
            <p>Join requests, decisions on your proposals, and work that's ready for you show up here.</p>
          </div>
        ) : (
          items.map((n) => <NotificationRow key={n.id} n={n} />)
        )}
      </div>

      {q.hasNextPage && (
        <button className="btn ghost" type="button" style={{ justifySelf: 'center' }} disabled={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
          {q.isFetchingNextPage ? 'Loading…' : 'Show older'}
        </button>
      )}
    </div>
    </div>
  )
}

function NotificationRow({ n }: { n: Notification }) {
  const tz = useTimezone()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { refreshUser } = useAuth()
  const to = targetOf(n)

  const open = () => {
    if (!n.read) {
      // Show it read at once; the server catches up.
      queryClient.setQueriesData<{ pages: NotificationPage[] }>({ queryKey: ['notifications'] }, (d) =>
        d && { ...d, pages: d.pages.map((p) => ({ ...p, items: p.items.map((x) => (x.id === n.id ? { ...x, read: true } : x)) })) },
      )
      void markNotificationRead(n.id).then(() => refreshUser(), () => {})
    }
    if (to) navigate(to)
  }

  const detail =
    n.type === 'proposal_rejected' && n.data?.reason ? (
      <span className="quote">{n.data.reason}</span>
    ) : n.type === 'temp_head_granted' && n.data?.expires_at ? (
      <span className="meta">Until {formatDay(n.data.expires_at, tz)}</span>
    ) : n.type === 'stages_unassigned' && n.data?.stages?.length ? (
      <span className="meta">{n.data.stages.map((s) => `${s.stage_title} (${s.task_title})`).join(', ')}</span>
    ) : null

  const body = (
    <>
      <span className={`notif-ico t-${n.type}`} aria-hidden="true">
        <Icon name={ICON[n.type] ?? 'bell'} size={16} />
      </span>
      <span className="main">
        <span className="title">{n.title}</span>
        {detail}
        <span className="meta">
          {n.room?.name && <>{n.room.name} · </>}
          <time dateTime={n.created_at} title={new Date(n.created_at).toLocaleString()}>
            {relativeTime(n.created_at, tz)}
          </time>
        </span>
      </span>
      {!n.read && <span className="unread-dot" aria-label="Unread" />}
      {to && <Icon name="chev" />}
    </>
  )

  // Always a button (keyboard and screen readers); items whose room is gone just get marked read.
  return (
    <button type="button" className={`row notif${to ? ' link' : ''}${n.read ? '' : ' unread'}`} onClick={open}>
      {body}
    </button>
  )
}

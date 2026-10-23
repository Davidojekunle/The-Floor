import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { NavLink, Outlet, useLocation, useMatch, useNavigate } from 'react-router-dom'
import type { RoomSummary } from '../api/auth'
import { getRoom, type Room } from '../api/rooms'
import { useAuth } from '../auth/useAuth'
import { formatDay } from '../lib/dates'
import { lastRoom } from '../lib/lastRoom'
import { useRoomExit } from '../room/roomExits'
import { roleLabel } from '../lib/labels'
import { useIsPhone } from '../lib/useMedia'
import { useTimezone } from '../lib/useTimezone'
import { Avatar } from './Avatar'
import { FeedbackDialog } from './FeedbackDialog'
import { Icon, type IconName } from './Icon'
import { usePushRouting } from '../lib/usePushRouting'
import { Menu, type MenuItem } from './Menu'
import { NewRoomDialog, PasteInviteDialog } from './RoomDialogs'
import { useToast } from './toastContext'

const MINI_KEY = 'floor-side-mini'

/**
 * The frame around every signed-in page (layout v3).
 * - Desktop: a dark sidebar for one room at a time (switcher on top, the room's pages below, account at the
 *   bottom), collapsible to an icon strip with the button or Ctrl+\. The pane scrolls, not the page.
 * - Phone: a translucent top bar (room switcher, account) and a bottom tab bar within thumb reach.
 *   Menus and dialogs open as sheets (see Menu, Dialog).
 * Outside a room (My work, all rooms) it keeps showing the last room, so its pages stay one tap away.
 */
export function Shell() {
  const { user } = useAuth()
  usePushRouting()
  const phone = useIsPhone()
  const location = useLocation()
  const match = useMatch('/rooms/:roomId/*')
  const pane = useRef<HTMLElement>(null)
  const [mini, setMini] = useState(() => {
    try {
      return localStorage.getItem(MINI_KEY) === '1'
    } catch {
      return false
    }
  })

  const remembered = lastRoom.get()
  const roomId = match?.params.roomId ?? (user?.rooms.some((r) => r.id === remembered) ? remembered : null)
  // Same query as RoomProvider, so it's fetched once and shared.
  const roomQuery = useQuery({ queryKey: ['room', roomId], queryFn: () => getRoom(roomId!), enabled: !!roomId, retry: false })
  // A room that's gone (deleted, left, removed) drops out of the sidebar at once, not just its page.
  const exit = useRoomExit(roomId ?? '')
  const gone = roomQuery.isError || (!!exit && exit.at > roomQuery.dataUpdatedAt)
  const room = gone ? undefined : roomQuery.data
  const summary = user?.rooms.find((r) => r.id === roomId)

  const toggleMini = () =>
    setMini((m) => {
      try {
        localStorage.setItem(MINI_KEY, m ? '0' : '1')
      } catch {
        // not remembered, that's all
      }
      return !m
    })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
        e.preventDefault()
        toggleMini()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  // A new page starts at the top (the pane scrolls, so the browser won't do it for us).
  useEffect(() => {
    pane.current?.scrollTo(0, 0)
  }, [location.pathname])

  const fill = /\/rooms\/[^/]+\/chat$/.test(location.pathname) // chat fills the pane, like Slack

  return (
    <div className={`shell${mini && !phone ? ' mini' : ''}`}>
      {!phone && <Sidebar room={room} summary={summary} mini={mini} onToggleMini={toggleMini} />}
      <div className="pane">
        {phone && <PhoneTop room={room} />}
        <main className={`pane-scroll${fill ? ' fill' : ''}`} ref={pane}>
          <Outlet />
        </main>
        {phone && <TabBar room={room} summary={summary} />}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- shared bits

function useNav(room?: Room, summary?: RoomSummary) {
  const { user } = useAuth()
  const can = (p: string) => room?.permissions.includes(p) ?? false
  const forYou = (user?.rooms ?? []).reduce((n, r) => n + r.mine_actionable, 0)
  const base = room ? `/rooms/${room.id}` : ''
  return {
    forYou,
    notifications: user?.unread_notifications ?? 0,
    base,
    unread: summary?.unread_messages ?? 0,
    pending: summary?.pending_count ?? 0,
    showRequests: can('join.manage') || can('task.approve'),
    showSettings: !!room, // everyone can leave a room from Settings
    showTemplates: can('task.create'),
  }
}

/** Task and template pages belong to Home, so Home stays highlighted there. */
function isRoomHome(path: string, base: string) {
  if (!base || !path.startsWith(base)) return false
  const rest = path.slice(base.length)
  return rest === '' || rest === '/' || rest.startsWith('/tasks')
}

function Count({ n, kind = 'attn' }: { n: number; kind?: 'attn' | 'msg' }) {
  if (n <= 0) return null
  return <span className={`side-badge ${kind === 'msg' ? 'is-msg' : kind}`}>{n > 99 ? '99+' : n}</span>
}

function RoomSwitcher({ room, variant }: { room?: Room; variant: 'side' | 'top' }) {
  const { user } = useAuth()
  const tz = useTimezone()
  const navigate = useNavigate()
  const location = useLocation()
  const [dialog, setDialog] = useState<'new' | 'paste' | null>(null)
  const rooms = user?.rooms ?? []
  // Other rooms that are waiting on you, so they still reach you from inside this one.
  const elsewhere = rooms.filter((r) => r.id !== room?.id && (r.pending_count > 0 || r.mine_actionable > 0)).length
  const elsewhereLabel = elsewhere === 1 ? '1 other room needs you' : `${elsewhere} other rooms need you`

  const switchTo = (id: string) => {
    // Stay on the same page when every member has it.
    const page = location.pathname.split('/')[3]
    navigate(`/rooms/${id}${page === 'chat' || page === 'calendar' || page === 'members' ? `/${page}` : ''}`)
  }

  const items: MenuItem[] = [
    ...rooms.map((r) => ({
      label: (
        <>
          <span className="room-sq sm">{r.name[0]}</span>
          <span className={`ri${r.unread_messages > 0 ? ' unread' : ''}`}>
            {r.name}
            <small>
              {r.my_role === 'temp_head' && r.temp_head_expires_at
                ? `Temp head until ${formatDay(r.temp_head_expires_at, tz)}`
                : roleLabel(r.my_role)}
              {r.unread_messages > 0 && ` · ${r.unread_messages} unread`}
            </small>
          </span>
          {r.pending_count + r.mine_actionable > 0 && <span className="count">{r.pending_count + r.mine_actionable}</span>}
          {r.id === room?.id && <Icon name="check" />}
        </>
      ),
      onSelect: () => switchTo(r.id),
    })),
    'divider',
    { label: iconLabel('grid', 'All rooms'), onSelect: () => navigate('/rooms') },
    { label: iconLabel('plus', 'New room'), onSelect: () => setDialog('new') },
    { label: iconLabel('link', 'Open an invite link'), onSelect: () => setDialog('paste') },
  ]

  const trigger =
    variant === 'side' ? (
      <>
        <span className="side-sq big">{room?.name[0] ?? '·'}</span>
        <span className="sw-text">
          <strong>{room?.name ?? 'Choose a room'}</strong>
          <small>{room ? roleLabel(room.my_role) : `${rooms.length} rooms`}</small>
        </span>
        {elsewhere > 0 && (
          <span className="sw-dot sw-count" title={elsewhereLabel}>
            <span className="sr-only">{elsewhereLabel}</span>
          </span>
        )}
        <span className="sw-chev">
          <Icon name="down" />
        </span>
        {elsewhere > 0 && <span className="mini-dot" />}
      </>
    ) : (
      <>
        <span className="room-sq sm">{room?.name[0] ?? '·'}</span>
        <span className="ptop-name">{room?.name ?? 'The Floor'}</span>
        <Icon name="down" />
        {elsewhere > 0 && <span className="ptop-dot" aria-label={`${elsewhere} other rooms need you`} />}
      </>
    )

  return (
    <>
      <Menu
        label={room ? `${room.name}: switch room` : 'Switch room'}
        labelTrigger={variant === 'side'}
        align="left"
        header="Your rooms"
        items={items}
        trigger={trigger}
        triggerClassName={variant === 'side' ? 'switcher' : 'ptop-switch'}
      />
      {dialog === 'new' && <NewRoomDialog onClose={() => setDialog(null)} />}
      {dialog === 'paste' && <PasteInviteDialog onClose={() => setDialog(null)} />}
    </>
  )
}

function iconLabel(icon: IconName, text: string) {
  return (
    <span className="mi">
      <Icon name={icon} />
      {text}
    </span>
  )
}

function AccountMenu({ variant }: { variant: 'side' | 'top' }) {
  const { user, logout, logoutEverywhere } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [feedback, setFeedback] = useState(false)
  if (!user) return null
  return (
    <>
      {feedback && <FeedbackDialog onClose={() => setFeedback(false)} />}
      <Menu
        label={`Account: ${user.name}`}
        labelTrigger={variant === 'side'}
        align="left"
        triggerClassName={variant === 'side' ? 'side-me' : 'icon-btn ptop-me'}
        trigger={
          variant === 'side' ? (
            <>
              <Avatar name={user.name} size="sm" />
              <span className="me-text">{user.name}</span>
            </>
          ) : (
            <>
              <Avatar name={user.name} size="sm" />
              <span className="sr-only">Account</span>
            </>
          )
        }
        header={
          <>
            <strong>{user.name}</strong>
            <br />
            {user.email}
          </>
        }
        items={[
          { label: 'Account settings', onSelect: () => navigate('/account') },
          ...(user.is_staff ? [{ label: 'Admin', onSelect: () => navigate('/admin') }] : []),
          { label: 'Send feedback', onSelect: () => setFeedback(true) },
          { label: 'Privacy', onSelect: () => navigate('/privacy') },
          'divider',
          { label: 'Sign out', onSelect: () => void logout() },
          {
            label: 'Sign out everywhere',
            onSelect: () => void logoutEverywhere().catch(() => toast("Couldn't sign out of your other devices. Try again.")),
          },
        ]}
      />
    </>
  )
}

// ---------------------------------------------------------------- desktop sidebar

function Sidebar(props: { room?: Room; summary?: RoomSummary; mini: boolean; onToggleMini: () => void }) {
  const { room, summary, mini, onToggleMini } = props
  const location = useLocation()
  const nav = useNav(room, summary)

  const item = (to: string, icon: IconName, label: string, extra?: ReactNode, opts?: { end?: boolean; active?: boolean }) => (
    <NavLink
      to={to}
      end={opts?.end}
      className={({ isActive }) => `side-item${(opts?.active ?? isActive) ? ' active' : ''}`}
      title={mini ? label : undefined}
    >
      <Icon name={icon} size={18} />
      <span className="nm">{label}</span>
      {extra}
    </NavLink>
  )

  return (
    <aside className="sidebar" aria-label="Navigation">
      <div className="side-top">
        <RoomSwitcher room={room} variant="side" />
      </div>
      <nav className="side-scroll" aria-label={room ? room.name : 'Main'}>
        {item('/my-work', 'task', 'My work', <>
          <Count n={nav.forYou} />
          {nav.forYou > 0 && <span className="mini-dot" />}
        </>)}
        {item('/notifications', 'bell', 'Notifications', <>
          <Count n={nav.notifications} kind="msg" />
          {nav.notifications > 0 && <span className="mini-dot is-msg" />}
        </>)}
        {room && (
          <>
            <div className="side-rule" />
            {item(nav.base, 'home', 'Home', null, { active: isRoomHome(location.pathname, nav.base) })}
            {item(`${nav.base}/chat`, 'chat', 'Chat', <>
              <Count n={nav.unread} kind="msg" />
              {nav.unread > 0 && <span className="mini-dot is-msg" />}
            </>)}
            {item(`${nav.base}/calendar`, 'calendar', 'Calendar')}
            {item(`${nav.base}/members`, 'users', 'Members')}
            {nav.showRequests &&
              item(`${nav.base}/requests`, 'inbox', 'Requests', <>
                <Count n={nav.pending} />
                {nav.pending > 0 && <span className="mini-dot" />}
              </>)}
            {nav.showTemplates && item(`${nav.base}/templates`, 'layers', 'Templates')}
            {nav.showSettings && item(`${nav.base}/settings`, 'gear', 'Settings')}
          </>
        )}
        {!room && (
          <>
            <div className="side-rule" />
            {item('/rooms', 'grid', 'All rooms', null, { end: true })}
          </>
        )}
      </nav>
      <div className="side-foot">
        <AccountMenu variant="side" />
        <button
          type="button"
          className="icon-btn side-mini-btn"
          onClick={onToggleMini}
          aria-label={mini ? 'Expand the sidebar' : 'Collapse the sidebar'}
          title={`${mini ? 'Expand' : 'Collapse'} (Ctrl+\\)`}
        >
          <Icon name="sidebar" size={18} />
        </button>
      </div>
    </aside>
  )
}

// ---------------------------------------------------------------- phone

function PhoneTop({ room }: { room?: Room }) {
  return (
    <header className="ptop">
      <RoomSwitcher room={room} variant="top" />
      <span className="spacer" />
      <BellLink />
      <AccountMenu variant="top" />
    </header>
  )
}

function BellLink() {
  const { user } = useAuth()
  const n = user?.unread_notifications ?? 0
  return (
    <NavLink to="/notifications" className="icon-btn ptop-bell" aria-label={n ? `Notifications, ${n} unread` : 'Notifications'}>
      <Icon name="bell" size={22} />
      {n > 0 && <span className="tab-badge is-msg">{n > 99 ? '99+' : n}</span>}
    </NavLink>
  )
}

function TabBar({ room, summary }: { room?: Room; summary?: RoomSummary }) {
  const location = useLocation()
  const navigate = useNavigate()
  const nav = useNav(room, summary)

  const tab = (to: string, icon: IconName, label: string, badge?: ReactNode, active?: boolean) => (
    <NavLink to={to} end className={({ isActive }) => `tab${(active ?? isActive) ? ' active' : ''}`}>
      <span className="tab-ico">
        <Icon name={icon} size={22} />
        {badge}
      </span>
      <span>{label}</span>
    </NavLink>
  )
  const dot = (n: number, kind: 'attn' | 'msg' = 'attn') => (n > 0 ? <span className={`tab-badge ${kind === 'msg' ? 'is-msg' : kind}`}>{n > 99 ? '99+' : n}</span> : null)

  const more: MenuItem[] = room
    ? [
        { label: iconLabel('users', 'Members'), onSelect: () => navigate(`${nav.base}/members`) },
        ...(nav.showRequests
          ? [{ label: iconLabel('inbox', nav.pending ? `Requests (${nav.pending})` : 'Requests'), onSelect: () => navigate(`${nav.base}/requests`) }]
          : []),
        ...(nav.showTemplates ? [{ label: iconLabel('layers', 'Templates'), onSelect: () => navigate(`${nav.base}/templates`) }] : []),
        ...(nav.showSettings ? [{ label: iconLabel('gear', 'Settings'), onSelect: () => navigate(`${nav.base}/settings`) }] : []),
        'divider' as const,
        { label: iconLabel('grid', 'All rooms'), onSelect: () => navigate('/rooms') },
      ]
    : []
  const moreActive = room ? /\/(members|requests|templates|settings)/.test(location.pathname) : false

  return (
    <nav className="tabbar" aria-label="Main">
      {room ? (
        <>
          {tab(nav.base, 'home', 'Home', null, isRoomHome(location.pathname, nav.base))}
          {tab(`${nav.base}/chat`, 'chat', 'Chat', dot(nav.unread, 'msg'))}
          {tab('/my-work', 'task', 'My work', dot(nav.forYou))}
          {tab(`${nav.base}/calendar`, 'calendar', 'Calendar')}
          <Menu
            label="More"
            header={room.name}
            items={more}
            triggerClassName={`tab${moreActive ? ' active' : ''}`}
            trigger={
              <>
                <span className="tab-ico">
                  <Icon name="moreCircle" size={22} />
                  {nav.showRequests && dot(nav.pending)}
                </span>
                <span>More</span>
              </>
            }
          />
        </>
      ) : (
        <>
          {tab('/rooms', 'grid', 'Rooms')}
          {tab('/my-work', 'task', 'My work', dot(nav.forYou))}
        </>
      )}
    </nav>
  )
}

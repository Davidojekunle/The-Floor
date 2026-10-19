import { Link } from 'react-router-dom'
import type { TaskListItem } from '../api/tasks'
import { useAuth } from '../auth/useAuth'
import { Avatar } from '../components/Avatar'
import { Icon } from '../components/Icon'
import { relativeTime } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'

export function ProposalPill({ status }: { status: TaskListItem['approval_status'] }) {
  if (status === 'pending') return <span className="pill pending">Waiting for approval</span>
  if (status === 'rejected') return <span className="pill rejected">Not approved</span>
  return null
}

/**
 * One proposal in a list.
 * - "mine": the proposer's own list (status, reason). `roomName` adds the room for cross-room lists.
 * - "review": an approver's queue (who proposed it, when, a Review button).
 */
export function ProposalRow({ task: t, href, mode, roomName }: { task: TaskListItem; href: string; mode: 'mine' | 'review'; roomName?: string }) {
  const { user } = useAuth()
  const tz = useTimezone()
  const when = t.submitted_at ? relativeTime(t.submitted_at, tz) : null
  const proposer = t.created_by.id === user?.id ? 'you' : t.created_by.name.split(' ')[0]

  if (mode === 'review')
    return (
      <Link className="row link" to={href}>
        <Avatar name={t.created_by.name} />
        <div className="main">
          <div className="title">{t.title}</div>
          <div className="meta">
            <span>Proposed by {proposer}</span>
            {when && (
              <>
                <span className="sep" />
                <span>{when}</span>
              </>
            )}
            <span className="sep" />
            <span>{t.stages_total === 1 ? '1 stage' : `${t.stages_total} stages`}</span>
          </div>
        </div>
        <span className="btn sm">Review</span>
      </Link>
    )

  return (
    <Link className="row link" to={href}>
      <div className="main">
        <div className="title">{t.title}</div>
        <div className="meta">
          <ProposalPill status={t.approval_status} />
          {roomName && <span>{roomName}</span>}
          {t.approval_status === 'pending' && when && <span>Sent {when}</span>}
          {t.approval_status === 'rejected' && t.rejection_reason && <span className="reason-inline">{t.rejection_reason}</span>}
        </div>
      </div>
      <Icon name="chev" />
    </Link>
  )
}

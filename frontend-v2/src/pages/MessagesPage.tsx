import { useQuery } from '@tanstack/react-query'
import { Link, Navigate } from 'react-router-dom'
import { listDmThreads } from '../api/dms'
import { useAuth } from '../auth/useAuth'
import { Avatar } from '../components/Avatar'
import { relativeTime } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'

/** Your private conversations, most recent first. Start one from a room's Members page. */
export function MessagesPage() {
  const { user } = useAuth()
  const tz = useTimezone()
  const threads = useQuery({ queryKey: ['dms'], queryFn: listDmThreads, enabled: !!user?.direct_messages })

  if (user && !user.direct_messages) return <Navigate to="/rooms" replace />

  return (
    <div className="container">
      <div className="page">
        <div className="page-head">
          <div>
            <h1>Messages</h1>
            <p className="sub">Private conversations. Start one from a room's Members page.</p>
          </div>
        </div>
        {threads.isPending ? (
          <div className="empty">
            <p>Loading…</p>
          </div>
        ) : threads.isError ? (
          <div className="empty">
            <p>Your messages didn't load. Refresh to try again.</p>
          </div>
        ) : threads.data.items.length === 0 ? (
          <div className="empty">
            <h2>No messages yet</h2>
            <p>Open a room's Members page and choose Message next to someone.</p>
          </div>
        ) : (
          <div className="card dm-list">
            {threads.data.items.map((t) => {
              const last = t.last_message
              const lastText = !last
                ? 'No messages yet'
                : last.deleted
                  ? 'Message deleted'
                  : `${last.sender_id === user?.id ? 'You: ' : ''}${last.body}`
              return (
                <Link key={t.id} to={`/messages/${t.id}`} className={`row link dm-row${t.unread ? ' unread' : ''}`}>
                  <Avatar name={t.other.name} />
                  <div className="main">
                    <div className="title">
                      {t.other.name}
                      {t.you_blocked && <span className="faint small"> · blocked</span>}
                    </div>
                    <div className="meta dm-last">{lastText}</div>
                  </div>
                  <div className="dm-side">
                    {t.last_message_at && <span className="faint small">{relativeTime(t.last_message_at, tz)}</span>}
                    {t.unread > 0 && <span className="tab-badge is-msg dm-badge">{t.unread > 99 ? '99+' : t.unread}</span>}
                  </div>
                </Link>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

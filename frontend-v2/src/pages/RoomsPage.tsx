import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { NewRoomDialog, PasteInviteDialog } from '../components/RoomDialogs'
import { formatDay } from '../lib/dates'
import { plural, roleLabel } from '../lib/labels'
import { useTimezone } from '../lib/useTimezone'

export function RoomsPage() {
  const { user } = useAuth()
  const tz = useTimezone()
  const [open, setOpen] = useState<'new' | 'paste' | null>(null)
  const rooms = user?.rooms ?? []

  return (
    <>
      <div className="container">
        <div className="page narrow">
          <div className="page-head">
            <h1>Your rooms</h1>
            {rooms.length > 0 && (
              <button className="btn primary" type="button" onClick={() => setOpen('new')}>
                <Icon name="plus" />
                New room
              </button>
            )}
          </div>

          {rooms.length === 0 ? (
            <div className="list">
              <div className="empty">
                <h2>You're not in any rooms yet</h2>
                <p>Start a room for your team, or open an invite link someone sent you.</p>
                <div className="empty-actions">
                  <button className="btn primary" type="button" onClick={() => setOpen('new')}>
                    Start a room
                  </button>
                  <button className="btn" type="button" onClick={() => setOpen('paste')}>
                    Open an invite link
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="list">
                {rooms.map((r) => (
                  <Link className="row link" to={`/rooms/${r.id}`} key={r.id}>
                    <span className="room-sq">{r.name[0]}</span>
                    <div className="main">
                      <div className="title">{r.name}</div>
                      <div className="meta">
                        {r.my_role === 'temp_head' && r.temp_head_expires_at
                          ? `Temp head until ${formatDay(r.temp_head_expires_at, tz)}`
                          : roleLabel(r.my_role)}
                        {r.unread_messages > 0 && (
                          <>
                            <span className="sep" />
                            <span>{r.unread_messages} unread</span>
                          </>
                        )}
                        {r.mine_actionable > 0 && (
                          <>
                            <span className="sep" />
                            <span>{plural(r.mine_actionable, 'task')} for you</span>
                          </>
                        )}
                      </div>
                    </div>
                    {r.pending_count > 0 && <span className="badge">{r.pending_count} waiting</span>}
                    <Icon name="chev" />
                  </Link>
                ))}
              </div>
              <p className="muted small" style={{ textAlign: 'center' }}>
                Got an invite link?{' '}
                <button className="link-btn" type="button" onClick={() => setOpen('paste')}>
                  Open it here
                </button>
              </p>
            </>
          )}
        </div>
      </div>

      {open === 'new' && <NewRoomDialog onClose={() => setOpen(null)} />}
      {open === 'paste' && <PasteInviteDialog onClose={() => setOpen(null)} />}
    </>
  )
}

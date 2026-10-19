import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { useCan, useRoom } from '../room/useRoom'

export function RoomLayout() {
  const { user, logout } = useAuth()
  const { room } = useRoom()
  const navigate = useNavigate()
  const canManageJoins = useCan('join.manage')
  const canManageInvite = useCan('invite.manage')

  const pending =
    user?.rooms.find((r) => r.id === room.id)?.pending_count ?? 0

  return (
    <div>
      <header className="room-header">
        <select
          aria-label="Switch room"
          value={room.id}
          onChange={(e) => navigate(`/rooms/${e.target.value}`)}
        >
          {user?.rooms.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>

        <nav>
          <NavLink to={`/rooms/${room.id}`} end>
            Home
          </NavLink>
          <NavLink to={`/rooms/${room.id}/members`}>Members</NavLink>
          {canManageJoins && (
            <NavLink to={`/rooms/${room.id}/join-requests`}>
              Join requests{pending > 0 && ` (${pending})`}
            </NavLink>
          )}
          {canManageInvite && (
            <NavLink to={`/rooms/${room.id}/settings`}>Settings</NavLink>
          )}
        </nav>

        <span className="spacer" />
        <Link to="/rooms">All rooms</Link>
        <button onClick={logout}>Log out</button>
      </header>

      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
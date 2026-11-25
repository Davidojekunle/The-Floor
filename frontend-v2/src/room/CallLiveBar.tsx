import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getCall } from '../api/calls'
import { useAuth } from '../auth/useAuth'
import { useRoom } from './roomContext'

/** Above the chat while the room's call is live: who's in, and Join. Hard to miss, unlike a header button. */
export function CallLiveBar() {
  const { room } = useRoom()
  const { user } = useAuth()
  const live = user?.calls_enabled ? user.rooms.find((r) => r.id === room.id)?.live_call : null
  const call = useQuery({ queryKey: ['call', room.id, live?.id], queryFn: () => getCall(room.id, live!.id), enabled: !!live })
  if (!live || (call.data && call.data.status !== 'live')) return null
  const people = call.data?.participants ?? []
  const who = people.length === 0 ? 'Nobody in yet' : people.length <= 3 ? people.map((p) => p.name).join(', ') : `${people.slice(0, 3).map((p) => p.name).join(', ')} +${people.length - 3}`
  return (
    <div className="call-live-bar" role="status">
      <span className="live-dot" aria-hidden="true" />
      <span className="call-live-text">
        <strong>Call in progress</strong> · {who}
      </span>
      <Link className="btn primary sm" to={`/rooms/${room.id}/calls/${live.id}`}>
        Join
      </Link>
    </div>
  )
}

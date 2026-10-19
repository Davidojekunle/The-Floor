import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, Outlet, useMatch, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getRoom } from '../api/rooms'
import { useAuth } from '../auth/useAuth'
import { lastRoom } from '../lib/lastRoom'
import { useRoomExit } from './roomExits'
import { RoomContext } from './roomContext'

export function RoomProvider() {
  const { roomId = '' } = useParams()
  const { user, refreshUser } = useAuth()
  const fullBleed = !!useMatch('/rooms/:roomId/chat') // chat fills the width, like Slack's main pane

  const query = useQuery({
    queryKey: ['room', roomId],
    queryFn: () => getRoom(roomId),
    retry: false,
  })

  const lostAccess = query.error instanceof ApiError && query.error.code === 'NOT_FOUND'

  // A 404 means we're not an active member (never were, or were removed). Refresh the room list.
  useEffect(() => {
    if (lostAccess) void refreshUser()
  }, [lostAccess, refreshUser])

  useEffect(() => {
    if (query.data) lastRoom.set(query.data.id)
  }, [query.data])
  const exit = useRoomExit(roomId)

  if (query.isPending) return null

  // The live event says why a room went away before any refetch could: show that at once. An exit only
  // counts if it's newer than the last good load, so someone who left and was let back in isn't stuck on it.
  const exited = !!exit && exit.at > query.dataUpdatedAt
  if (query.isError || exited) {
    const knownName = user?.rooms.find((r) => r.id === roomId)?.name ?? exit?.name
    const name = knownName ?? 'This room'
    // The live event told us why, when it could: deleted, left (in another tab), or removed.
    const [title, body] = !lostAccess && !exited
      ? ["This room didn't load", query.error?.message ?? 'Try again in a moment.']
      : exit?.reason === 'room_deleted'
        ? [`${name} was deleted`, 'Its head deleted the room, with all its tasks and chat. Your other rooms are fine.']
        : exit?.reason === 'left'
          ? [`You left ${name}`, 'To come back, ask to join again with the invite link.']
          : exit?.reason === 'removed'
            ? [`You were removed from ${name}`, 'Ask the head if you think this was a mistake.']
            : ["You don't have access to this room", `${name} isn't one of your rooms any more, or the link is wrong.`]
    return (
      <>
        <div className="container">
          <div className="empty" style={{ paddingTop: 96 }}>
            <h2>{title}</h2>
            <p>{body}</p>
            {lostAccess || exited ? (
              <Link className="btn" to="/rooms" style={{ marginTop: 8 }}>
                Go to your rooms
              </Link>
            ) : (
              <button className="btn" type="button" onClick={() => void query.refetch()} style={{ marginTop: 8 }}>
                Try again
              </button>
            )}
          </div>
        </div>
      </>
    )
  }

  return (
    <RoomContext.Provider value={{ room: query.data, refreshRoom: () => void query.refetch() }}>
      <div className={fullBleed ? 'full-bleed' : 'container'}>
        <Outlet />
      </div>
    </RoomContext.Provider>
  )
}

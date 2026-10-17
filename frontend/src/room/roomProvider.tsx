import { useQuery } from '@tanstack/react-query'
import { Link, Outlet, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getRoom } from '../api/room'
import { RoomContext } from './roomContext'

export function RoomProvider() {
  const { roomId = '' } = useParams()

  const query = useQuery({
    queryKey: ['room', roomId],
    queryFn: () => getRoom(roomId),
    retry: false,
  })

  if (query.isPending) return <p className="page">Loading room...</p>

  if (query.isError) {
    const notFound =
      query.error instanceof ApiError && query.error.status === 404
    return (
      <div className="auth-page">
        <div className="card">
          <h1>{notFound ? 'Room not found' : 'Something went wrong'}</h1>
          <p>
            {notFound
              ? "This room doesn't exist, or you're not an active member."
              : query.error.message}
          </p>
          <Link to="/rooms">Back to my rooms</Link>
        </div>
      </div>
    )
  }

  return (
    <RoomContext.Provider
      value={{
        room: query.data,
        refreshRoom: () => {
          void query.refetch()
        },
      }}
    >
      <Outlet />
    </RoomContext.Provider>
  )
}
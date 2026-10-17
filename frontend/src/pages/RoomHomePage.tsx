import { useRoom } from '../room/useRoom'

export function RoomHomePage() {
  const { room } = useRoom()

  return (
    <div>
      {room.temp_head_expires_at && (
        <div className="banner">
          You have temporary head access until{' '}
          {new Date(room.temp_head_expires_at).toLocaleDateString()}.
        </div>
      )}
      <h1>{room.name}</h1>
      <p>
        {room.member_count} members · you are {room.my_role.replace('_', ' ')}
      </p>
      <p>Tasks and the calendar will appear here once the backend supports them.</p>
    </div>
  )
}
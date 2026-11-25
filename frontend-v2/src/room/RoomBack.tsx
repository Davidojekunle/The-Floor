import { Link } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { useRoom } from './roomContext'

/** Pages reached from the phone's "More" menu: a way back to the room (the sidebar does this on desktop). */
export function RoomBack() {
  const { room } = useRoom()
  return (
    <div className="room-back">
      <Link className="back" to={`/rooms/${room.id}`}>
        <Icon name="back" />
        {room.name}
      </Link>
    </div>
  )
}

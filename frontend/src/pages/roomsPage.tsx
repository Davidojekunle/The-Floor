import { useAuth } from '../auth/useAuth'

export function RoomsPage() {
  const { user, logout } = useAuth()

  return (
    <div className="page">
      <h1>Hi, {user?.name}</h1>

      {user?.rooms.length === 0 ? (
        <p>You are not in any room yet.</p>
      ) : (
        <ul>
          {user?.rooms.map((room) => (
            <li key={room.id}>
              {room.name} ({room.my_role})
            </li>
          ))}
        </ul>
      )}

      <button onClick={logout}>Log out</button>
    </div>
  )
}
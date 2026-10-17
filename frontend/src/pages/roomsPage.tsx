import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { createRoom } from '../api/room'
import { useAuth } from '../auth/useAuth'

export function RoomsPage() {
  const { user, logout, refreshUser } = useAuth()
  const [name, setName] = useState('')

  const create = useMutation({
    mutationFn: (roomName: string) => createRoom(roomName),
    onSuccess: async () => {
      setName('')
      await refreshUser()
    },
  })

  function handleCreate(e: FormEvent) {
    e.preventDefault()
    create.mutate(name.trim())
  }

  return (
    <div className="page">
      <h1>Hi, {user?.name}</h1>

      <h2>Your rooms</h2>
      {user?.rooms.length === 0 ? (
        <p>You are not in any room yet.</p>
      ) : (
        <ul>
          {user?.rooms.map((room) => (
            <li key={room.id}>
              <Link to={`/rooms/${room.id}`}>{room.name}</Link> ({room.my_role})
              {room.pending_count > 0 && <strong> · {room.pending_count} waiting</strong>}
            </li>
          ))}
        </ul>
      )}

      <h2>Create a room</h2>
      <form onSubmit={handleCreate}>
        {create.error && (
          <div className="form-error">
            {create.error instanceof ApiError
              ? create.error.message
              : 'Something went wrong.'}
          </div>
        )}
        <div className="field">
          <label htmlFor="room-name">Room name</label>
          <input
            id="room-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <button className="primary" type="submit" disabled={create.isPending}>
          {create.isPending ? 'Creating...' : 'Create room'}
        </button>
      </form>

      <p>
        <button onClick={logout}>Log out</button>
      </p>
    </div>
  )
}
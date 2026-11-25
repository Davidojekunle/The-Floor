import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { renameRoom } from '../api/rooms'
import { useAuth } from '../auth/useAuth'
import { useToast } from '../components/toastContext'
import { useCan, useRoom } from './roomContext'

/** Settings: the head renames the room. */
export function RenameRoom() {
  const { room, refreshRoom } = useRoom()
  const { refreshUser } = useAuth()
  const can = useCan('room.rename')
  const toast = useToast()
  const [name, setName] = useState(room.name)
  const [error, setError] = useState<string>()
  const save = useMutation({
    mutationFn: () => renameRoom(room.id, name.trim()),
    onSuccess: (r) => {
      refreshRoom()
      void refreshUser().catch(() => {})
      setName(r.name)
      toast(`Renamed to ${r.name}.`)
    },
    onError: (e) => setError(e instanceof ApiError ? (e.fields?.name ?? e.message) : "Couldn't rename the room. Try again."),
  })
  if (!can) return null
  const changed = name.trim() && name.trim() !== room.name
  return (
    <section className="form-card">
      <div>
        <h2>Room name</h2>
        <p className="muted small" style={{ marginTop: 4 }}>
          Everyone sees the new name, and the chat says it changed.
        </p>
      </div>
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault()
          if (changed) save.mutate()
        }}
      >
        <label htmlFor="room-name" className="sr-only">
          Room name
        </label>
        <div className="invite-field">
          <input className="input" id="room-name" maxLength={100} value={name} aria-invalid={error ? true : undefined}
            onChange={(e) => {
              setName(e.target.value)
              setError(undefined)
            }} />
          <button className="btn primary" type="submit" disabled={!changed || save.isPending}>
            {save.isPending ? 'Saving…' : 'Rename'}
          </button>
        </div>
        {error && (
          <span className="err" role="alert">
            {error}
          </span>
        )}
      </form>
    </section>
  )
}

import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { createRoom } from '../api/rooms'
import { useAuth } from '../auth/useAuth'
import { Dialog } from './Dialog'
import { useToast } from './toastContext'

/** Start a room, or open an invite link. Used by the rooms page and the room switcher. */
export function NewRoomDialog({ onClose }: { onClose: () => void }) {
  const { refreshUser } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: (value: string) => createRoom(value),
    onSuccess: async (room) => {
      await refreshUser()
      toast(`${room.name} is ready. Share this link to invite people.`)
      // The head's next job is inviting people, so open the invite link.
      navigate(`/rooms/${room.id}/settings`)
    },
    onError: (err) =>
      setError(err instanceof ApiError && err.code === 'VALIDATION_ERROR' ? 'Use 1 to 100 characters.' : (err as Error).message),
  })

  const submit = () => {
    if (!name.trim()) return setError('Give the room a name.')
    create.mutate(name.trim())
  }

  return (
    <Dialog
      title="New room"
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" onClick={submit} disabled={create.isPending}>
            {create.isPending ? 'Creating…' : 'Create room'}
          </button>
        </>
      }
    >
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <label htmlFor="room-name">Room name</label>
        <input
          className="input"
          id="room-name"
          maxLength={100}
          autoFocus
          placeholder="e.g. Studio Alpha"
          value={name}
          onChange={(e) => {
            setName(e.target.value)
            setError(null)
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby="room-name-hint"
        />
        <span className={error ? 'err' : 'hint'} id="room-name-hint" role={error ? 'alert' : undefined}>
          {error ?? "You'll be the head. Next, you'll get a link to invite people."}
        </span>
      </form>
    </Dialog>
  )
}

export function PasteInviteDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = () => {
    // Accept a full link or just the code: take the last path segment.
    const code = value.trim().replace(/[?#].*$/, '').replace(/\/+$/, '').split('/').pop() ?? ''
    if (!code) return setError('Paste the link someone sent you.')
    navigate(`/join/${encodeURIComponent(code)}`)
  }

  return (
    <Dialog
      title="Open an invite link"
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" onClick={submit}>
            Continue
          </button>
        </>
      }
    >
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <label htmlFor="invite-link">Invite link</label>
        <input
          className="input"
          id="invite-link"
          autoFocus
          placeholder="thefloor.app/join/…"
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            setError(null)
          }}
          aria-invalid={error ? true : undefined}
        />
        {error && (
          <span className="err" role="alert">
            {error}
          </span>
        )}
      </form>
    </Dialog>
  )
}

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { listMembers, type Member } from '../api/members'
import { deleteRoom, leaveRoom, transferHead } from '../api/rooms'
import { useAuth } from '../auth/useAuth'
import { ConfirmDialog, Dialog } from '../components/Dialog'
import { useToast } from '../components/toastContext'
import { lastRoom } from '../lib/lastRoom'
import { useRoom } from './roomContext'
import { roomExits, type ExitReason } from './roomExits'
import { useRoomError } from './useRoomError'

/** After leaving or deleting: go to the rooms list first (so the room's screens don't flash "no access"), then tidy up. */
function useExitRoom() {
  const { room } = useRoom()
  const { refreshUser } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  return (reason: ExitReason, message: string) => {
    roomExits.markOwn(room.id, reason, room.name)
    lastRoom.forget(room.id)
    navigate('/rooms', { replace: true })
    for (const key of ['room', 'tasks', 'task', 'members', 'tags', 'join-requests', 'templates', 'updates', 'activity'])
      queryClient.removeQueries({ queryKey: [key, room.id] })
    void queryClient.invalidateQueries({ queryKey: ['me-tasks'] })
    void refreshUser()
    toast(message)
  }
}

export function LeaveRoomDialog({ onClose }: { onClose: () => void }) {
  const { room } = useRoom()
  const onError = useRoomError()
  const exit = useExitRoom()
  const [error, setError] = useState<string | null>(null)
  const leave = useMutation({
    mutationFn: () => leaveRoom(room.id),
    onSuccess: () => exit('left', `You left ${room.name}.`),
    onError: (err) =>
      setError(
        err instanceof ApiError && err.code === 'HEAD_MUST_TRANSFER'
          ? "You're the head. Hand headship to someone else before leaving."
          : onError(err),
      ),
  })
  return (
    <ConfirmDialog
      title={`Leave ${room.name}?`}
      body="Your tags and stage assignments here are removed, and you stop seeing its tasks and chat. Your messages stay. To come back, ask to join again with the invite link."
      confirmLabel="Leave room"
      pending={leave.isPending}
      error={error}
      onConfirm={() => leave.mutate()}
      onClose={onClose}
    />
  )
}

export function TransferHeadDialog({ initial, onClose }: { initial?: Member; onClose: () => void }) {
  const { room } = useRoom()
  const { user, refreshUser } = useAuth()
  const queryClient = useQueryClient()
  const toast = useToast()
  const onError = useRoomError()
  const members = useQuery({ queryKey: ['members', room.id], queryFn: () => listMembers(room.id) })
  const others = (members.data?.items ?? []).filter((m) => m.user.id !== user?.id)
  const [pick, setPick] = useState(initial?.membership_id ?? '')
  const chosen = others.find((m) => m.membership_id === pick)
  const [error, setError] = useState<string | null>(null)

  const transfer = useMutation({
    mutationFn: () => transferHead(room.id, pick),
    onSuccess: (updated) => {
      queryClient.setQueryData(['room', room.id], updated) // my new role and permissions
      for (const key of ['members', 'tasks', 'join-requests']) void queryClient.invalidateQueries({ queryKey: [key, room.id] })
      void refreshUser()
      toast(`${chosen?.user.name ?? 'They'} now lead${chosen ? 's' : ''} ${room.name}. You're a member here now.`)
      onClose()
    },
    onError: (err) => setError(err instanceof ApiError && err.fields?.membership_id ? err.fields.membership_id : onError(err)),
  })

  return (
    <Dialog
      title="Transfer headship"
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" disabled={!chosen || transfer.isPending} onClick={() => transfer.mutate()}>
            {chosen ? `Make ${chosen.user.name.split(' ')[0]} the head` : 'Make head'}
          </button>
        </>
      }
    >
      <div className="field">
        <label htmlFor="new-head">New head</label>
        <select
          className="select"
          id="new-head"
          value={pick}
          onChange={(e) => {
            setPick(e.target.value)
            setError(null)
          }}
          disabled={members.isPending}
        >
          <option value="">{members.isPending ? 'Loading people…' : 'Choose a member'}</option>
          {others.map((m) => (
            <option key={m.membership_id} value={m.membership_id}>
              {m.user.name}
            </option>
          ))}
        </select>
        <span className="hint">
          A room has one head. You'll become a member and lose head rights here
          {chosen?.role === 'temp_head' ? `, and ${chosen.user.name.split(' ')[0]}'s temporary head grant ends` : ''}.
        </span>
      </div>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
    </Dialog>
  )
}

export function DeleteRoomDialog({ onClose }: { onClose: () => void }) {
  const { room } = useRoom()
  const onError = useRoomError()
  const exit = useExitRoom()
  const [typed, setTyped] = useState('')
  const [error, setError] = useState<string | null>(null)
  const norm = (v: string) => v.trim().split(/\s+/).join(' ').toLowerCase()
  const matches = norm(typed) === norm(room.name)

  const remove = useMutation({
    mutationFn: () => deleteRoom(room.id, typed),
    onSuccess: () => exit('room_deleted', `${room.name} was deleted.`),
    onError: (err) => setError(err instanceof ApiError && err.fields?.confirm_name ? err.fields.confirm_name : onError(err)),
  })

  return (
    <Dialog
      title={`Delete ${room.name}?`}
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn danger" type="button" disabled={!matches || remove.isPending} onClick={() => remove.mutate()}>
            Delete room
          </button>
        </>
      }
    >
      <p className="muted">
        Every task, stage, message, tag and template in {room.name} is deleted for everyone. Members keep their accounts and other
        rooms. This can't be undone.
      </p>
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault()
          if (matches) remove.mutate()
        }}
      >
        <label htmlFor="confirm-name">
          Type <strong>{room.name}</strong> to confirm
        </label>
        <input
          className="input"
          id="confirm-name"
          autoComplete="off"
          spellCheck={false}
          value={typed}
          aria-invalid={error ? true : undefined}
          onChange={(e) => {
            setTyped(e.target.value)
            setError(null)
          }}
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

import { useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { regenerateInvite } from '../api/rooms'
import { ConfirmDialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { useToast } from '../components/toastContext'
import { useCan, useRoom } from '../room/roomContext'
import { EmailInvite } from '../room/EmailInvite'
import { DeleteRoomDialog, LeaveRoomDialog, TransferHeadDialog } from '../room/RoomLifecycle'
import { Switch } from '../components/Switch'
import { useNotificationSettings } from '../room/useNotificationSettings'
import { useRoomError } from '../room/useRoomError'

export function SettingsPage() {
  const { room, refreshRoom } = useRoom()
  const canInvite = useCan('invite.manage')
  const canTransfer = useCan('head.transfer')
  const canDelete = useCan('room.delete')
  const isHead = room.my_role === 'head'
  const [dialog, setDialog] = useState<'leave' | 'transfer' | 'delete' | null>(null)
  const notif = useNotificationSettings()
  const muted = notif.settings?.muted_rooms.includes(room.id) ?? false
  const toast = useToast()
  const onError = useRoomError()
  const [copied, setCopied] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const reset = useMutation({
    mutationFn: () => regenerateInvite(room.id),
    onSuccess: () => {
      refreshRoom()
      setConfirmReset(false)
      toast('New link ready. The old one no longer works.')
    },
    onError: (err) => toast(onError(err)),
  })

  // Every member can open Settings (to leave); the invite link, headship and deleting depend on permissions.
  const url = `${window.location.origin}/join/${room.invite_code}`

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      input.current?.select()
      toast('Press Ctrl+C to copy the selected link.')
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Settings</h1>
          <p className="sub">{room.name}</p>
        </div>
      </div>

      {canInvite && room.invite_code && (
      <>
      <section className="form-card">
        <div>
          <h2>Invite link</h2>
          <p className="muted small" style={{ marginTop: 4 }}>
            Anyone with this link can ask to join. You approve each person.
          </p>
        </div>
        <div className="invite-field">
          <label htmlFor="invite-url" className="sr-only">
            Invite link
          </label>
          <input className="input" id="invite-url" readOnly value={url} ref={input} onFocus={(e) => e.target.select()} />
          <button className="btn" type="button" onClick={copy}>
            <Icon name={copied ? 'check' : 'copy'} />
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </section>

      <EmailInvite />

      <section className="form-card setting">
        <div style={{ minWidth: 0, flex: '1 1 280px' }}>
          <h2>Reset the link</h2>
          <p className="muted small" style={{ marginTop: 4 }}>
            Makes a new link. The current one, and any invites you've emailed, stop working.
          </p>
        </div>
        <button className="btn danger-outline" type="button" onClick={() => setConfirmReset(true)}>
          Reset link
        </button>
      </section>
      </>
      )}

      {notif.settings && (
        <section className="form-card">
          <Switch
            label="Mute this room"
            detail="No bell items or emails from this room. Its counts still show in your room list."
            checked={muted}
            onChange={(on) => notif.setMuted({ roomId: room.id, on })}
          />
        </section>
      )}

      {canTransfer && (
        <section className="form-card setting">
          <div style={{ minWidth: 0, flex: '1 1 280px' }}>
            <h2>Transfer headship</h2>
            <p className="muted small" style={{ marginTop: 4 }}>
              Make another member the head. You'll become a member.
            </p>
          </div>
          <button className="btn" type="button" onClick={() => setDialog('transfer')}>
            Transfer headship
          </button>
        </section>
      )}

      <section className="form-card setting">
        <div style={{ minWidth: 0, flex: '1 1 280px' }}>
          <h2>Leave this room</h2>
          <p className="muted small" style={{ marginTop: 4 }}>
            {isHead
              ? "You're the head, so hand headship to someone else first."
              : 'You stop seeing its tasks and chat. You can ask to join again with the invite link.'}
          </p>
        </div>
        {isHead ? (
          canTransfer && (
            <button className="btn" type="button" onClick={() => setDialog('transfer')}>
              Transfer, then leave
            </button>
          )
        ) : (
          <button className="btn danger-outline" type="button" onClick={() => setDialog('leave')}>
            Leave room
          </button>
        )}
      </section>

      {canDelete && (
        <section className="form-card setting danger-zone">
          <div style={{ minWidth: 0, flex: '1 1 280px' }}>
            <h2>Delete this room</h2>
            <p className="muted small" style={{ marginTop: 4 }}>
              Deletes every task, message and template in {room.name} for everyone. This can't be undone.
            </p>
          </div>
          <button className="btn danger-outline" type="button" onClick={() => setDialog('delete')}>
            Delete room
          </button>
        </section>
      )}

      {dialog === 'leave' && <LeaveRoomDialog onClose={() => setDialog(null)} />}
      {dialog === 'transfer' && <TransferHeadDialog onClose={() => setDialog(null)} />}
      {dialog === 'delete' && <DeleteRoomDialog onClose={() => setDialog(null)} />}

      {confirmReset && (
        <ConfirmDialog
          title="Reset the invite link?"
          body="The current link stops working immediately. Anyone who hasn't used it yet will need the new one."
          confirmLabel="Reset link"
          pending={reset.isPending}
          onConfirm={() => reset.mutate()}
          onClose={() => setConfirmReset(false)}
        />
      )}
    </div>
  )
}

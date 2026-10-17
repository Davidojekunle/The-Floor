import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { regenerateInvite } from '../api/room'
import { useCan, useRoom } from '../room/useRoom'

export function RoomSettingsPage() {
  const { room, refreshRoom } = useRoom()
  const canManageInvite = useCan('invite.manage')
  const [copied, setCopied] = useState(false)

  const regenerate = useMutation({
    mutationFn: () => regenerateInvite(room.id),
    onSuccess: () => refreshRoom(),
  })

  if (!canManageInvite || !room.invite_code) {
    return <p>You don't have access to room settings.</p>
  }

  const inviteUrl = `${window.location.origin}/join/${room.invite_code}`

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(inviteUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard unavailable, the user can copy the text by hand
    }
  }

  function handleRegenerate() {
    const ok = window.confirm(
      'Generate a new invite link? The old link will stop working immediately.',
    )
    if (ok) regenerate.mutate()
  }

  return (
    <div>
      <h1>Room settings</h1>

      <h2>Invite link</h2>
      {regenerate.error && (
        <div className="form-error">
          {regenerate.error instanceof ApiError
            ? regenerate.error.message
            : 'Something went wrong.'}
        </div>
      )}
      <p>
        <code>{inviteUrl}</code>
      </p>
      <div className="actions">
        <button onClick={copyLink}>{copied ? 'Copied!' : 'Copy link'}</button>
        <button onClick={handleRegenerate} disabled={regenerate.isPending}>
          {regenerate.isPending ? 'Generating...' : 'Generate new link'}
        </button>
      </div>
    </div>
  )
}
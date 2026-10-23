import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { inviteByEmail } from '../api/rooms'
import { useToast } from '../components/toastContext'
import { plural } from '../lib/labels'
import { useRoom } from './roomContext'
import { useRoomError } from './useRoomError'

const MAX = 20
const looksLikeEmail = (s: string) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s)

/** Settings: email the invite link. People invited this way are let straight in, no approval. */
export function EmailInvite() {
  const { room } = useRoom()
  const toast = useToast()
  const onRoomError = useRoomError()
  const [text, setText] = useState('')
  const [error, setError] = useState<string>()

  const emails = [...new Set(text.split(/[\s,;]+/).map((s) => s.trim().toLowerCase()).filter(Boolean))]
  const send = useMutation({
    mutationFn: () => inviteByEmail(room.id, emails),
    onSuccess: ({ invited, already_members }) => {
      setText('')
      const sent = invited.length ? `Invite sent to ${invited.length === 1 ? invited[0] : plural(invited.length, 'person', 'people')}.` : ''
      const skipped = already_members.length ? ` ${already_members.join(', ')} ${already_members.length === 1 ? 'is' : 'are'} already in the room.` : ''
      toast((sent + skipped).trim())
    },
    onError: (err) =>
      setError(
        err instanceof ApiError && err.code === 'RATE_LIMITED'
          ? "That's a lot of invites for one hour. Try again later."
          : err instanceof ApiError && err.code === 'VALIDATION_ERROR'
            ? 'One of those addresses isn\'t valid.'
            : onRoomError(err),
      ),
  })

  const submit = () => {
    if (!emails.length) return setError('Add at least one email address.')
    const bad = emails.find((e) => !looksLikeEmail(e))
    if (bad) return setError(`${bad} doesn't look like an email address.`)
    if (emails.length > MAX) return setError(`Up to ${MAX} at a time.`)
    send.mutate()
  }

  return (
    <section className="form-card">
      <div>
        <h2>Invite by email</h2>
        <p className="muted small" style={{ marginTop: 4 }}>
          We email them the link. If they sign in with that address, they're let straight in.
        </p>
      </div>
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <label htmlFor="invite-emails" className="sr-only">
          Email addresses
        </label>
        <div className="invite-field">
          <input
            className="input"
            id="invite-emails"
            type="text"
            inputMode="email"
            autoComplete="off"
            placeholder="tola@example.com, bisi@example.com"
            value={text}
            aria-invalid={error ? true : undefined}
            aria-describedby="invite-emails-hint"
            onChange={(e) => {
              setText(e.target.value)
              setError(undefined)
            }}
          />
          <button className="btn primary" type="submit" disabled={send.isPending}>
            {send.isPending ? 'Sending…' : 'Send'}
          </button>
        </div>
        {error ? (
          <span className="err" id="invite-emails-hint" role="alert">
            {error}
          </span>
        ) : (
          <span className="hint" id="invite-emails-hint">
            Separate several with commas. Invites work for 30 days.
          </span>
        )}
      </form>
    </section>
  )
}

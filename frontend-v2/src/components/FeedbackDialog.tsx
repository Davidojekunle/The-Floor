import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { sendFeedback, type FeedbackKind } from '../api/feedback'
import { SUPPORT_EMAIL } from '../lib/support'
import { Dialog } from './Dialog'
import { useToast } from './toastContext'

const KINDS: { value: FeedbackKind; label: string }[] = [
  { value: 'problem', label: 'Problem' },
  { value: 'idea', label: 'Idea' },
  { value: 'other', label: 'Other' },
]

const PLACEHOLDER: Record<FeedbackKind, string> = {
  problem: 'What happened, and what did you expect?',
  idea: 'What would make The Floor better for you?',
  other: "What's on your mind?",
}

/** "Send feedback": goes to the team's inbox with the page it came from, without leaving the app. */
export function FeedbackDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast()
  const [kind, setKind] = useState<FeedbackKind>('other')
  const [message, setMessage] = useState('')
  const [error, setError] = useState<string>()
  const send = useMutation({
    mutationFn: () => sendFeedback({ kind, message: message.trim(), page: window.location.pathname }),
    onSuccess: () => {
      toast("Thanks, we got it. We'll reply by email if we need to.")
      onClose()
    },
    onError: (e) =>
      setError(
        e instanceof ApiError && e.code === 'RATE_LIMITED'
          ? "That's a lot of feedback for one hour. Try again later, or email us."
          : "Couldn't send it. Try again, or email us.",
      ),
  })
  const submit = () => {
    if (!message.trim()) return setError('Write something first.')
    send.mutate()
  }

  return (
    <Dialog
      title="Send feedback"
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" disabled={send.isPending} onClick={submit}>
            {send.isPending ? 'Sending…' : 'Send'}
          </button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
        style={{ display: 'grid', gap: 16 }}
      >
        <div className="seg" role="radiogroup" aria-label="What kind of feedback">
          {KINDS.map((k) => (
            <button key={k.value} type="button" role="radio" aria-checked={kind === k.value} onClick={() => setKind(k.value)}>
              {k.label}
            </button>
          ))}
        </div>
        <div className="field">
          <label htmlFor="feedback-msg" className="sr-only">
            Your feedback
          </label>
          <textarea
            className="textarea"
            id="feedback-msg"
            rows={5}
            maxLength={4000}
            autoFocus
            placeholder={PLACEHOLDER[kind]}
            value={message}
            aria-invalid={error ? true : undefined}
            aria-describedby="feedback-hint"
            onChange={(e) => {
              setMessage(e.target.value)
              setError(undefined)
            }}
          />
          {error ? (
            <span className="err" id="feedback-hint" role="alert">
              {error}
            </span>
          ) : (
            <span className="hint" id="feedback-hint">
              We'll see your name, email and the page you're on. Or email{' '}
              <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>.
            </span>
          )}
        </div>
        <button type="submit" hidden />
      </form>
    </Dialog>
  )
}

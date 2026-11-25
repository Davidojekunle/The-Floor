import { useRef, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { askAssistant, getAssistantStatus, type AssistantReply, type AssistantTurn, type DraftTaskOut } from '../api/assistant'
import { ApiError } from '../api/client'
import { listMembers, listTags } from '../api/members'
import { useRoom } from './roomContext'
import { newStage, type DraftTask } from './taskDraft'

const EXAMPLES = [
  'Freshers week reel: Femi writes the script by Friday, Tola films, the editor edits, Amara posts by the 5th',
  'Group assignment due next Thursday. Ada does the intro, Kemi the research, I put it together',
]

/** The assistant's draft as form state. Ids were checked by the server; unknown owners come back empty. */
export function draftToForm(d: DraftTaskOut): DraftTask {
  return {
    title: d.title,
    due: d.due_date,
    description: d.description,
    stages: d.stages.map((s, i) =>
      newStage({
        title: s.title,
        owner: s.assignee_id ? `user:${s.assignee_id}` : s.tag_id ? `tag:${s.tag_id}` : '',
        due: s.due_date ?? '',
        showDue: !!s.due_date,
        parallel: i > 0 && s.parallel_with_previous,
      }),
    ),
  }
}

/**
 * "Describe your task": type it like you'd say it in the group chat (or paste the message). The assistant
 * asks when something's unclear, then shows what it understood; only after "Yes, fill it in" does the form
 * below change. The admin switch decides who has it; 5 new descriptions per room per week.
 */
export function TaskAssistant({ onConfirm }: { onConfirm: (d: DraftTask) => void }) {
  const { room } = useRoom()
  const queryClient = useQueryClient()
  const status = useQuery({ queryKey: ['assistant', room.id], queryFn: () => getAssistantStatus(room.id) })
  const members = useQuery({ queryKey: ['members', room.id], queryFn: () => listMembers(room.id) })
  const tags = useQuery({ queryKey: ['tags', room.id], queryFn: () => listTags(room.id) })
  const [history, setHistory] = useState<AssistantTurn[]>([])
  const [reply, setReply] = useState<AssistantReply | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const box = useRef<HTMLTextAreaElement>(null)

  const usesLeft = reply?.uses_left ?? status.data?.uses_left
  const starting = !reply
  const outOfUses = starting && usesLeft === 0

  async function send(e?: FormEvent) {
    e?.preventDefault()
    const said = text.trim()
    if (!said || busy) return
    const messages: AssistantTurn[] = [...history, { role: 'user', text: said }]
    setBusy(true)
    setError(null)
    try {
      const r = await askAssistant(room.id, { conversation_id: reply?.conversation_id, messages })
      setHistory([...messages, { role: 'assistant', text: r.message }])
      setReply(r)
      setText('')
      setDone(false)
      void queryClient.invalidateQueries({ queryKey: ['assistant', room.id] })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The assistant didn't answer. Try again.")
    } finally {
      setBusy(false)
      box.current?.focus()
    }
  }

  function startOver() {
    setHistory([])
    setReply(null)
    setText('')
    setError(null)
    setDone(false)
  }

  const who = (s: DraftTaskOut['stages'][number]) => {
    if (s.assignee_id) return members.data?.items.find((m) => m.user.id === s.assignee_id)?.user.name ?? 'Someone'
    if (s.tag_id) return `Everyone tagged ${tags.data?.items.find((t) => t.id === s.tag_id)?.name ?? '…'}`
    return 'Nobody yet'
  }

  const canAnswer = reply && reply.turns_left > 0 && !done
  const outOfTurns = reply && reply.turns_left === 0 && reply.kind === 'questions'

  return (
    <section className="form-card assistant" aria-labelledby="assistant-h">
      <div className="assistant-head">
        <div>
          <h2 id="assistant-h">Describe your task</h2>
          <p className="muted small">
            Type it like you'd say it in the group chat, or paste the message. You'll check it before anything changes.
          </p>
        </div>
        {usesLeft !== undefined && (
          <span className="assistant-left small muted">
            {usesLeft} of {status.data?.limit ?? 5} left this week
          </span>
        )}
      </div>

      {history.length > 0 && (
        <ol className="assistant-thread" aria-live="polite">
          {history.map((m, i) => (
            <li key={i} className={m.role === 'user' ? 'me' : 'it'}>
              {m.text}
            </li>
          ))}
        </ol>
      )}

      {reply?.kind === 'draft' && reply.draft && !done && (
        <div className="assistant-draft">
          <div className="assistant-draft-title">
            <strong>{reply.draft.title}</strong>
            <span className="muted small"> · due {reply.draft.due_date}</span>
          </div>
          <ol>
            {reply.draft.stages.map((s, i) => (
              <li key={i}>
                <span>{s.title}</span>
                <span className="muted small">
                  {who(s)}
                  {s.due_date ? ` · ${s.due_date}` : ''}
                  {s.parallel_with_previous ? ' · alongside the previous stage' : ''}
                </span>
              </li>
            ))}
          </ol>
          <div className="assistant-actions">
            <button
              type="button"
              className="btn primary"
              onClick={() => {
                onConfirm(draftToForm(reply.draft!))
                setDone(true)
              }}
            >
              Yes, fill it in
            </button>
            {reply.turns_left > 0 && (
              <button type="button" className="btn ghost" onClick={() => box.current?.focus()}>
                Change something
              </button>
            )}
          </div>
        </div>
      )}

      {done && (
        <p className="small assistant-done">
          Filled in below. Check it, change anything you need, then create it.{' '}
          <button type="button" className="link-btn" onClick={startOver}>
            Describe another
          </button>
        </p>
      )}

      {outOfUses ? (
        <p className="small muted">This room has used its descriptions for this week. You can still use the form below.</p>
      ) : outOfTurns ? (
        <p className="small muted">
          That's as many questions as one description gets. Use the form below, or{' '}
          <button type="button" className="link-btn" onClick={startOver}>
            start again
          </button>
          .
        </p>
      ) : (
        (starting || canAnswer) && (
          <form className="assistant-input" onSubmit={send}>
            <label className="sr-only" htmlFor="assistant-text">
              {starting ? 'Describe the task' : 'Your answer'}
            </label>
            <textarea
              id="assistant-text"
              ref={box}
              rows={starting ? 3 : 2}
              maxLength={2000}
              value={text}
              placeholder={starting ? EXAMPLES[0] : reply?.kind === 'draft' ? 'What should change?' : 'Your answer'}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void send()
              }}
              disabled={busy}
            />
            <div className="assistant-actions">
              <button type="submit" className="btn primary" disabled={busy || !text.trim()}>
                {busy ? 'Thinking…' : starting ? 'Draft it' : 'Send'}
              </button>
              {!starting && (
                <button type="button" className="btn ghost" onClick={startOver} disabled={busy}>
                  Start over
                </button>
              )}
            </div>
          </form>
        )
      )}
      {starting && !outOfUses && (
        <p className="small muted assistant-example">Another example: "{EXAMPLES[1]}"</p>
      )}
      {error && (
        <p className="err small" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}

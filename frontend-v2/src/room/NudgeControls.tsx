import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ackNudge, nudgeStage, type Stage, type TaskDetail } from '../api/tasks'
import { Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { useToast } from '../components/toastContext'
import { relativeTime } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'
import { useActionError } from './useRoomError'

function useTaskUpdate(task: TaskDetail) {
  const queryClient = useQueryClient()
  return (updated: TaskDetail) => {
    queryClient.setQueryData(['task', task.room_id, task.id], updated)
    void queryClient.invalidateQueries({ queryKey: ['tasks', task.room_id] })
    void queryClient.invalidateQueries({ queryKey: ['me-tasks'] })
  }
}

/** Heads: a Nudge (or "Ask about the block") button on late, stuck or blocked stages, and when it was last sent. */
export function NudgeButton({ task, stage: s }: { task: TaskDetail; stage: Stage }) {
  const toast = useToast()
  const tz = useTimezone()
  const onError = useActionError(task.room_id)
  const apply = useTaskUpdate(task)
  const [open, setOpen] = useState(false)
  const send = useMutation({
    mutationFn: (note: string) => nudgeStage(task.room_id, task.id, s.id, note || undefined),
    onSuccess: (updated) => {
      apply(updated)
      setOpen(false)
      toast(s.nudge_kind === 'block' ? `Asked about the block on ${s.title}.` : `Nudged the people on ${s.title}.`)
    },
    onError: (err) => toast(onError(err)),
  })

  if (!s.nudge_kind) return null
  const recent = s.nudge && !s.can_nudge
  return (
    <>
      {s.can_nudge ? (
        <button className="btn sm" type="button" onClick={() => setOpen(true)}>
          <Icon name="bell" />
          {s.nudge_kind === 'block' ? 'Ask about the block' : 'Nudge'}
        </button>
      ) : (
        recent && (
          <span className="faint small">
            Nudged {relativeTime(s.nudge!.at, tz)}
            {s.nudge!.open ? '' : ' · answered'}
          </span>
        )
      )}
      {open && <NudgeDialog stage={s} pending={send.isPending} onClose={() => setOpen(false)} onSend={(note) => send.mutate(note)} />}
    </>
  )
}

function NudgeDialog(props: { stage: Stage; pending: boolean; onClose: () => void; onSend: (note: string) => void }) {
  const [note, setNote] = useState('')
  const block = props.stage.nudge_kind === 'block'
  const who = props.stage.assignees.length
    ? props.stage.assignees.map((a) => a.name).join(', ')
    : props.stage.tag
      ? `Everyone with ${props.stage.tag.name}`
      : 'The people on this stage'
  return (
    <Dialog
      title={block ? `Ask about the block on ${props.stage.title}?` : `Nudge ${props.stage.title}?`}
      onClose={props.onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={props.onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" disabled={props.pending} onClick={() => props.onSend(note.trim())}>
            Send nudge
          </button>
        </>
      }
    >
      <p className="muted">
        {who} will get a private notification{block ? ' asking about the block' : ' asking for an update'}. It isn't posted in the room chat.
      </p>
      <div className="field">
        <label htmlFor="nudge-note">
          Note <span className="faint" style={{ fontWeight: 400 }}>(optional)</span>
        </label>
        <input
          className="input"
          id="nudge-note"
          maxLength={200}
          autoFocus
          placeholder={block ? 'e.g. Is there anything I can chase for you?' : 'e.g. The event is on Friday'}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <span className="hint">You can nudge a stage once a day.</span>
      </div>
    </Dialog>
  )
}

/** The people on a stage: an open nudge, with a one-tap "I'm on it". Updates and blocking answer it too. */
export function NudgeBanner({ task, stage: s }: { task: TaskDetail; stage: Stage }) {
  const toast = useToast()
  const tz = useTimezone()
  const onError = useActionError(task.room_id)
  const apply = useTaskUpdate(task)
  const ack = useMutation({
    mutationFn: () => ackNudge(task.room_id, task.id, s.id),
    onSuccess: (updated) => {
      apply(updated)
      toast(`${s.nudge?.by?.name ?? 'They'} will see you're on it.`)
    },
    onError: (err) => toast(onError(err)),
  })
  if (!s.involves_me || !s.nudge?.open) return null
  const by = s.nudge.by?.name ?? 'A head'
  return (
    <div className="nudge-banner" role="status">
      <Icon name="bell" />
      <div className="nudge-text">
        <strong>
          {by} {s.nudge.kind === 'block' ? 'asked about the block' : 'asked for an update'}
        </strong>
        <span className="faint"> · {relativeTime(s.nudge.at, tz)}</span>
        {s.nudge.note && <div className="nudge-note">“{s.nudge.note}”</div>}
        <div className="faint small">Starting it, finishing it, posting an update or marking it blocked also answers.</div>
      </div>
      {s.nudge.kind === 'update' && (
        <button className="btn sm primary" type="button" disabled={ack.isPending} onClick={() => ack.mutate()}>
          I'm on it
        </button>
      )}
    </div>
  )
}

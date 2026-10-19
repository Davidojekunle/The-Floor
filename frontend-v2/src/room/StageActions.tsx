import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { setStageStatus, type Stage, type StageStatus, type TaskDetail } from '../api/tasks'

/** The fields StageActions needs. Both a task-detail stage and a /me/tasks stage have them. */
type ActionableStage = Pick<Stage, 'id' | 'title' | 'status' | 'allowed_statuses'>
import { Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { Menu } from '../components/Menu'
import { useToast } from '../components/toastContext'
import { PRIMARY_TRANSITION, TRANSITION_LABEL } from '../lib/labels'
import { useAuth } from '../auth/useAuth'
import { useActionError } from './useRoomError'
import { DoneDialog } from './StageResult'

/**
 * Buttons for one stage. Only what the server lists in allowed_statuses is shown:
 * one primary button, the rest in a "…" menu. The client never works out transitions itself.
 */
export function StageActions({ roomId, taskId, stage }: { roomId: string; taskId: string; stage: ActionableStage }) {
  const queryClient = useQueryClient()
  const { refreshUser } = useAuth()
  const toast = useToast()
  const onError = useActionError(roomId)
  const [blocking, setBlocking] = useState(false)
  const [finishing, setFinishing] = useState(false)

  const mutation = useMutation({
    mutationFn: (v: { to: Exclude<StageStatus, 'locked'>; reason?: string; result?: { url: string; note?: string } }) =>
      setStageStatus(roomId, taskId, stage.id, v.to, v.reason, v.result),
    onSuccess: (updated, v) => {
      // The response is the whole task, so the detail cache is updated without refetching it.
      queryClient.setQueryData(['task', roomId, taskId], updated)
      void queryClient.invalidateQueries({ queryKey: ['tasks', roomId] })
      void queryClient.invalidateQueries({ queryKey: ['me-tasks'] })
      void refreshUser() // "for you" counts
      setBlocking(false)
      setFinishing(false)
      toast(statusToast(updated, stage, v.to))
    },
    onError: (err) => toast(onError(err)),
  })

  const allowed = stage.allowed_statuses
  if (!allowed.length) return null

  const primary = PRIMARY_TRANSITION[stage.status]
  const rest = allowed.filter((to) => to !== primary)
  const run = (to: StageStatus) =>
    to === 'blocked' ? setBlocking(true) : to === 'done' ? setFinishing(true) : mutation.mutate({ to: to as Exclude<StageStatus, 'locked'> })
  const label = (to: StageStatus) => TRANSITION_LABEL[`${stage.status}>${to}`] ?? to

  return (
    <>
      {primary && allowed.includes(primary) && (
        <button
          type="button"
          className={`btn sm ${stage.status === 'todo' || stage.status === 'in_progress' ? 'primary' : ''}`}
          disabled={mutation.isPending}
          onClick={() => run(primary)}
        >
          {stage.status === 'in_progress' && <Icon name="check" />}
          {label(primary)}
        </button>
      )}
      {rest.length > 0 && (
        <Menu label={`More actions for ${stage.title}`} items={rest.map((to) => ({ label: label(to), onSelect: () => run(to) }))} />
      )}
      {finishing && (
        <DoneDialog
          stage={stage}
          pending={mutation.isPending}
          onClose={() => setFinishing(false)}
          onDone={(url, note) => mutation.mutate({ to: 'done', result: url ? { url, note } : undefined })}
        />
      )}
      {blocking && (
        <BlockDialog
          pending={mutation.isPending}
          onClose={() => setBlocking(false)}
          onSubmit={(reason) => mutation.mutate({ to: 'blocked', reason })}
        />
      )}
    </>
  )
}

function BlockDialog({ pending, onClose, onSubmit }: { pending: boolean; onClose: () => void; onSubmit: (r: string) => void }) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const submit = () => {
    if (!reason.trim()) return setError('Add a short reason so the head knows what to fix.')
    onSubmit(reason.trim())
  }
  return (
    <Dialog
      title="What's blocking this stage?"
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" onClick={submit} disabled={pending}>
            Mark as blocked
          </button>
        </>
      }
    >
      <div className="field">
        <label htmlFor="block-reason">Reason</label>
        <textarea
          className="textarea"
          id="block-reason"
          maxLength={300}
          autoFocus
          placeholder="e.g. Waiting on the logo files from the client"
          value={reason}
          aria-invalid={error ? true : undefined}
          aria-describedby="block-reason-hint"
          onChange={(e) => {
            setReason(e.target.value)
            setError(null)
          }}
        />
        <span className={error ? 'err' : 'hint'} id="block-reason-hint" role={error ? 'alert' : undefined}>
          {error ?? "Heads see this on the room's home page."}
        </span>
      </div>
    </Dialog>
  )
}

function statusToast(after: TaskDetail, stage: ActionableStage, to: StageStatus): string {
  if (to === 'done') {
    if (after.status === 'done') return `${after.title} is complete.`
    // Stages in the next step that are now ready were unlocked by this one.
    const step = after.stages.find((s) => s.id === stage.id)?.step ?? 0
    const unlocked = after.stages.filter((s) => s.status === 'todo' && s.step === step + 1)
    return unlocked.length
      ? `${stage.title} is done. ${unlocked.map((s) => s.title).join(' and ')} can start now.`
      : `${stage.title} is done.`
  }
  if (to === 'blocked') return `${stage.title} is marked as blocked.`
  if (stage.status === 'blocked') return `Blocker cleared on ${stage.title}.`
  if (stage.status === 'done') return `${stage.title} reopened.`
  if (stage.status === 'locked') return `${stage.title} unlocked early.`
  if (to === 'in_progress') return `You started ${stage.title}.`
  return `${stage.title} moved back to To do.`
}

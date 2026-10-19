import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  approveTask,
  createTemplate,
  deleteTask,
  getTask,
  rejectTask,
  resubmitTask,
  type Stage,
  type TaskDetail,
} from '../api/tasks'
import { useAuth } from '../auth/useAuth'
import { ConfirmDialog, Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { Menu, type MenuItem } from '../components/Menu'
import { useToast } from '../components/toastContext'
import { dueLabel, formatDay, relativeTime } from '../lib/dates'
import { plural, statusLabel } from '../lib/labels'
import { useTimezone } from '../lib/useTimezone'
import { useCan, useRoom } from '../room/roomContext'
import { StageActions } from '../room/StageActions'
import { NudgeBanner, NudgeButton } from '../room/NudgeControls'
import { googleCalendarEventUrl, openInNewTab } from '../lib/googleCalendar'
import { StageUpdates, TaskUpdatesFeed } from '../room/StageUpdates'
import { useRoomError } from '../room/useRoomError'

export function TaskPage() {
  const { taskId = '' } = useParams()
  const { room } = useRoom()
  const { user } = useAuth()
  const tz = useTimezone()
  const canSaveTemplate = useCan('task.create')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const onError = useRoomError()
  const [confirmDelete, setConfirmDelete] = useState(false)

  const query = useQuery({ queryKey: ['task', room.id, taskId], queryFn: () => getTask(room.id, taskId), retry: false })
  const t = query.data
  const isProposal = !!t && t.approval_status !== 'approved'
  const isMyProposal = isProposal && t.created_by.id === user?.id

  const remove = useMutation({
    mutationFn: () => deleteTask(room.id, taskId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tasks', room.id] })
      void queryClient.invalidateQueries({ queryKey: ['me-tasks'] })
      queryClient.removeQueries({ queryKey: ['task', room.id, taskId] })
      toast(isMyProposal ? 'Proposal withdrawn.' : `"${t?.title}" was deleted.`)
      navigate(`/rooms/${room.id}`)
    },
    onError: (err) => toast(onError(err)),
  })

  const saveTemplate = useMutation({
    mutationFn: (task: TaskDetail) =>
      createTemplate(room.id, {
        name: task.title,
        stages: task.stages.map((s) => ({ title: s.title, tag_id: s.tag?.id ?? null, parallel_with_previous: s.parallel_with_previous })),
      }),
    onSuccess: (tpl) => {
      void queryClient.invalidateQueries({ queryKey: ['templates', room.id] })
      toast(`Saved as the template "${tpl.name}".`)
    },
    onError: (err) =>
      toast(err instanceof ApiError && err.status === 409 ? 'A template with this name already exists.' : onError(err)),
  })

  const back = (
    <div>
      <Link className="back" to={`/rooms/${room.id}`}>
        <Icon name="back" />
        {room.name}
      </Link>
    </div>
  )

  if (query.isPending) return <div className="page">{back}</div>
  if (query.isError || !t) {
    const missing = query.error instanceof ApiError && query.error.code === 'NOT_FOUND'
    return (
      <div className="page">
        {back}
        <div className="empty">
          <h2>{missing ? "This task doesn't exist any more" : "This task didn't load"}</h2>
          <p>{missing ? 'It may have been deleted, or it was a proposal you can no longer see.' : query.error?.message}</p>
        </div>
      </div>
    )
  }

  // Everything below is driven by the server's flags, not by room roles: proposers get rights their role lacks.
  const noun = isProposal ? 'proposal' : 'task'
  const items: MenuItem[] = []
  if (t.can_edit) items.push({ label: `Edit ${noun}`, onSelect: () => navigate(`/rooms/${room.id}/tasks/${t.id}/edit`) })
  if (!isProposal && canSaveTemplate) items.push({ label: 'Save as template', onSelect: () => saveTemplate.mutate(t) })
  if (!isProposal && t.status !== 'done')
    items.push({
      label: 'Add due date to Google Calendar',
      onSelect: () =>
        openInNewTab(
          googleCalendarEventUrl({
            title: t.title,
            dueIso: t.due_date,
            timeZone: tz,
            details: `Due in ${room.name} on The Floor.`,
            link: `${window.location.origin}/rooms/${room.id}/tasks/${t.id}`,
          }),
        ),
    })
  if (t.can_delete && !isMyProposal) // a proposer withdraws from the decision bar instead
    items.push('divider', { label: `Delete ${noun}`, danger: true, onSelect: () => setConfirmDelete(true) })

  return (
    <div className="page">
      {back}
      <div className="page-head" style={{ alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          <h1>{t.title}</h1>
          <div className="task-meta">
            <span className={t.is_overdue ? 'flag-late' : undefined}>{dueLabel(t.due_date, tz, t.is_overdue)}</span>
            {t.is_overdue && (
              <>
                <span className="sep" />
                <span>Was due {formatDay(t.due_date, tz)}</span>
              </>
            )}
            <span className="sep" />
            <span>
              {isProposal ? 'Proposed' : 'Created'} by {t.created_by.id === user?.id ? 'you' : t.created_by.name}
            </span>
          </div>
        </div>
        {items.length > 0 && <Menu label="Task actions" triggerClassName="btn" trigger={<Icon name="more" />} items={items} />}
      </div>

      {t.description && <p className="desc">{t.description}</p>}

      {isProposal ? (
        <DecisionBar task={t} onWithdraw={() => setConfirmDelete(true)} />
      ) : (
        <div className="prog-block">
          <div className="lbl">
            <span>
              {t.stages_done} of {plural(t.stages_total, 'stage')} done
            </span>
            <span>{t.progress}%</span>
          </div>
          <div className={`bar lg ${t.status === 'done' ? 'done' : ''}`}>
            <span style={{ width: `${t.progress}%` }} />
          </div>
        </div>
      )}

      <section className="section">
        <h2>Stages</h2>
        <ol className="timeline">
          {t.stages.map((s, i) => (
            <StageItem key={s.id} task={t} stage={s} previous={t.stages[i - 1]} tz={tz} planned={isProposal} />
          ))}
        </ol>
      </section>

      {!isProposal && <TaskUpdatesFeed task={t} />}

      {confirmDelete && (
        <ConfirmDialog
          title={isMyProposal ? `Withdraw "${t.title}"?` : `Delete "${t.title}"?`}
          body={
            isMyProposal
              ? "The proposal is deleted and the heads won't see it any more."
              : isProposal
                ? `The proposal and its ${plural(t.stages_total, 'stage')} are deleted. This can't be undone.`
                : `The task and its ${plural(t.stages_total, 'stage')} are deleted for everyone. This can't be undone.`
          }
          confirmLabel={isMyProposal ? 'Withdraw' : `Delete ${noun}`}
          pending={remove.isPending}
          onConfirm={() => remove.mutate()}
          onClose={() => setConfirmDelete(false)}
        />
      )}
    </div>
  )
}

/** Shown instead of the progress bar while a task is a proposal (pending or rejected). */
function DecisionBar({ task: t, onWithdraw }: { task: TaskDetail; onWithdraw: () => void }) {
  const { room } = useRoom()
  const { user, refreshUser } = useAuth()
  const tz = useTimezone()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const onError = useRoomError()
  const [rejecting, setRejecting] = useState(false)

  const first = t.created_by.name.split(' ')[0]
  const when = t.submitted_at ? relativeTime(t.submitted_at, tz) : null
  const decider = t.decided_by ? (t.decided_by.id === user?.id ? 'you' : t.decided_by.name) : null

  const done = (updated: TaskDetail, message: string) => {
    queryClient.setQueryData(['task', room.id, t.id], updated)
    void queryClient.invalidateQueries({ queryKey: ['tasks', room.id] })
    void queryClient.invalidateQueries({ queryKey: ['me-tasks'] })
    void refreshUser() // Requests badge and "for you" counts
    toast(message)
  }

  const approve = useMutation({
    mutationFn: () => approveTask(room.id, t.id),
    onSuccess: (updated) => {
      const ready = updated.stages.filter((s) => s.status === 'todo').map((s) => s.title)
      done(updated, ready.length ? `Approved. ${ready.join(' and ')} can start now.` : 'Approved.')
    },
    onError: (err) => toast(onError(err)),
  })
  const reject = useMutation({
    mutationFn: (reason: string) => rejectTask(room.id, t.id, reason || undefined),
    onSuccess: (updated, reason) => {
      setRejecting(false)
      done(updated, `"${t.title}" was rejected.${reason ? ` ${first} will see your reason.` : ''}`)
    },
    onError: (err) => toast(onError(err)),
  })
  const resubmit = useMutation({
    mutationFn: () => resubmitTask(room.id, t.id),
    onSuccess: (updated) => done(updated, 'Sent for approval again.'),
    onError: (err) => toast(onError(err)),
  })
  const busy = approve.isPending || reject.isPending || resubmit.isPending
  const editHref = `/rooms/${room.id}/tasks/${t.id}/edit`

  let what
  let acts
  if (t.can_decide && t.approval_status === 'pending') {
    what = (
      <>
        <strong>
          {first} proposed this{when ? ` ${when}` : ''}
        </strong>
        <span className="muted small">Approve it to add it to the room's tasks. Its first stage can start straight away.</span>
      </>
    )
    acts = (
      <>
        <button className="btn ghost" type="button" disabled={busy} onClick={() => setRejecting(true)}>
          Reject
        </button>
        <button className="btn primary" type="button" disabled={busy} onClick={() => approve.mutate()}>
          <Icon name="check" />
          Approve
        </button>
      </>
    )
  } else if (t.approval_status === 'pending') {
    what = (
      <>
        <strong>Waiting for approval</strong>
        <span className="muted small">
          {when ? `Sent ${when}. ` : ''}Only you and the room's heads can see it until it's approved.
        </span>
      </>
    )
    acts = (
      <>
        {t.can_delete && (
          <button className="btn ghost" type="button" onClick={onWithdraw}>
            Withdraw
          </button>
        )}
        {t.can_edit && (
          <button className="btn" type="button" onClick={() => navigate(editHref)}>
            Edit
          </button>
        )}
      </>
    )
  } else {
    what = (
      <>
        <strong>Not approved{decider ? ` by ${decider}` : ''}</strong>
        {t.rejection_reason && <span className="quote">{t.rejection_reason}</span>}
        <span className="muted small">
          {t.can_decide
            ? `${first} can change it and send it again. You can still approve it now.`
            : t.can_resubmit
              ? 'Change it if you like, then send it again.'
              : null}
        </span>
      </>
    )
    acts = (
      <>
        {t.can_decide && (
          <button className="btn" type="button" disabled={busy} onClick={() => approve.mutate()}>
            Approve anyway
          </button>
        )}
        {!t.can_decide && t.can_delete && (
          <button className="btn ghost" type="button" onClick={onWithdraw}>
            Withdraw
          </button>
        )}
        {!t.can_decide && t.can_edit && (
          <button className="btn" type="button" onClick={() => navigate(editHref)}>
            Edit
          </button>
        )}
        {t.can_resubmit && (
          <button className="btn primary" type="button" disabled={busy} onClick={() => resubmit.mutate()}>
            Send again
          </button>
        )}
      </>
    )
  }

  return (
    <>
      <div className={`decision ${t.approval_status}`} role="status">
        <div className="what">{what}</div>
        <div className="acts">{acts}</div>
      </div>
      {rejecting && (
        <RejectDialog
          title={t.title}
          proposer={first}
          pending={reject.isPending}
          onClose={() => setRejecting(false)}
          onSubmit={(reason) => reject.mutate(reason)}
        />
      )}
    </>
  )
}

function RejectDialog(props: { title: string; proposer: string; pending: boolean; onClose: () => void; onSubmit: (r: string) => void }) {
  const [reason, setReason] = useState('')
  return (
    <Dialog
      title={`Reject "${props.title}"?`}
      onClose={props.onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={props.onClose}>
            Cancel
          </button>
          <button className="btn danger" type="button" disabled={props.pending} onClick={() => props.onSubmit(reason.trim())}>
            Reject
          </button>
        </>
      }
    >
      <div className="field">
        <label htmlFor="reject-reason">
          Reason <span className="faint" style={{ fontWeight: 400 }}>(optional)</span>
        </label>
        <textarea
          className="textarea"
          id="reject-reason"
          maxLength={500}
          autoFocus
          placeholder="e.g. Let's do this next quarter"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <span className="hint">{props.proposer} will see this, and can change the proposal and send it again.</span>
      </div>
    </Dialog>
  )
}

function StageItem({ task, stage: s, previous, tz, planned }: { task: TaskDetail; stage: Stage; previous?: Stage; tz: string; planned: boolean }) {
  const { user } = useAuth()
  const isModerator = useCan('stage.edit')
  const waitingOn = task.stages.filter((x) => x.step === s.step - 1).map((x) => x.title)
  const people = s.assignees.map((a) => (a.id === user?.id ? 'You' : a.name))
  // A proposal's stages can't move yet, so they're shown as "Planned" with no actions or waiting notes.
  const status = planned ? 'locked' : s.status

  return (
    <li className={`stage is-${status}`}>
      <span className="marker" aria-hidden="true">
        {status === 'done' ? <Icon name="check" size={13} bold /> : status === 'blocked' ? '!' : null}
      </span>
      <div className="stage-body">
        <div className="stage-top">
          <span className="stage-title">{s.title}</span>
          <span className={`status ${planned ? 'planned' : s.status}`}>{planned ? 'Planned' : statusLabel(s.status)}</span>
          {s.parallel_with_previous && previous && (
            <span className="par-note">
              <Icon name="parallel" size={14} />
              At the same time as {previous.title}
            </span>
          )}
        </div>
        <div className="owner">
          {s.tag && <span className="tag">{s.tag.name}</span>}
          {people.length > 0 && <span>{people.join(', ')}</span>}
          {!s.tag && !people.length && <span className="faint">No one assigned yet</span>}
          {s.due_date && (
            <>
              <span className="sep" />
              <span className={s.is_overdue && !planned ? 'flag-late' : undefined}>{dueLabel(s.due_date, tz, s.is_overdue && !planned)}</span>
            </>
          )}
          {s.involves_me && !planned && s.status !== 'done' && (
            <>
              <span className="sep" />
              <button
                className="link-btn"
                type="button"
                onClick={() =>
                  openInNewTab(
                    googleCalendarEventUrl({
                      title: `${s.title} · ${task.title}`,
                      dueIso: s.due_date ?? task.due_date,
                      timeZone: tz,
                      details: 'Your stage on The Floor.',
                      link: `${window.location.origin}/rooms/${task.room_id}/tasks/${task.id}`,
                    }),
                  )
                }
              >
                Add to Google Calendar
              </button>
            </>
          )}
          {s.status === 'done' && s.completed_by && (
            <>
              <span className="sep" />
              <span>Done by {s.completed_by.id === user?.id ? 'you' : s.completed_by.name}</span>
            </>
          )}
        </div>
        {s.status === 'blocked' && s.blocked_reason && <div className="reason">{s.blocked_reason}</div>}
        {!planned && <NudgeBanner task={task} stage={s} />}
        {!planned && isModerator && s.nudge_kind && (
          <div className="stage-actions">
            <NudgeButton task={task} stage={s} />
          </div>
        )}
        {!planned &&
          (s.status === 'locked' && !s.can_update_status ? (
            <span className="faint small">
              Starts when {waitingOn.join(' and ') || 'the previous stage'} {waitingOn.length > 1 ? 'are' : 'is'} done
            </span>
          ) : (
            s.can_update_status && (
              <div className="stage-actions">
                <StageActions roomId={task.room_id} taskId={task.id} stage={s} />
              </div>
            )
          ))}
        {!planned && <StageUpdates task={task} stage={s} canPost={s.involves_me || isModerator} />}
      </div>
    </li>
  )
}

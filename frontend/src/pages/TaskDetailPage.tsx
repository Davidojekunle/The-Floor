import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { errorMessage } from '../api/errorMessage'
import {
  getTask,
  setStageStatus,
  type Stage,
  type StageStatus,
} from '../api/tasks'
import { ProgressBar } from '../components/ProgressBar'
import { actionLabel, formatDateTime, statusLabel } from '../lib/format'
import { useRoom } from '../room/useRoom'

export function TaskDetailPage() {
  const { taskId = '' } = useParams()
  const { room, refreshRoom } = useRoom()
  const queryClient = useQueryClient()
  const taskKey = ['task', room.id, taskId]
  const [blockingId, setBlockingId] = useState<string | null>(null)
  const [reason, setReason] = useState('')

  const task = useQuery({
    queryKey: taskKey,
    queryFn: () => getTask(room.id, taskId),
    retry: false,
  })

  const change = useMutation({
    mutationFn: (vars: {
      stageId: string
      status: StageStatus
      reason?: string
    }) => setStageStatus(room.id, taskId, vars.stageId, vars.status, vars.reason),
    onSuccess: async (updated) => {
      // The response is the whole task, so no second fetch is needed.
      queryClient.setQueryData(taskKey, updated)
      setBlockingId(null)
      setReason('')
      await queryClient.invalidateQueries({ queryKey: ['tasks', room.id] })
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 403) refreshRoom()
      // 403 or 409 usually means our copy was stale, so reload it.
      if (err instanceof ApiError && (err.status === 403 || err.status === 409)) {
        void queryClient.invalidateQueries({ queryKey: taskKey })
      }
    },
  })

  function handleAction(stage: Stage, target: StageStatus) {
    if (target === 'blocked') {
      setBlockingId(stage.id)
      setReason('')
      return
    }
    change.mutate({ stageId: stage.id, status: target })
  }

  function handleBlockSubmit(e: FormEvent) {
    e.preventDefault()
    if (blockingId) {
      change.mutate({
        stageId: blockingId,
        status: 'blocked',
        reason: reason.trim(),
      })
    }
  }

  if (task.isPending) return <p>Loading task...</p>

  if (task.isError) {
    const notFound =
      task.error instanceof ApiError && task.error.status === 404
    return (
      <div>
        <p>{notFound ? 'Task not found.' : 'Could not load this task.'}</p>
        <Link to={`/rooms/${room.id}`}>Back to tasks</Link>
      </div>
    )
  }

  const t = task.data

  return (
    <div>
      <p>
        <Link to={`/rooms/${room.id}`}>&larr; Back to tasks</Link>
      </p>

      <h1>{t.title}</h1>
      <p>
        {t.status === 'done' && <span className="badge done">Done</span>}
        {t.is_blocked && <span className="badge blocked">Blocked</span>}
        {t.is_overdue && <span className="badge overdue">Overdue</span>}
      </p>
      {t.description && <p>{t.description}</p>}

      <ProgressBar value={t.progress} />
      <p className="muted">
        {t.stages_done} of {t.stages_total} stages
        {t.start_date ? ` · starts ${formatDateTime(t.start_date)}` : ''} · due{' '}
        {formatDateTime(t.due_date)} · created by {t.created_by.name}
      </p>

      <h2>Stages</h2>

      {change.error && (
        <div className="form-error">{errorMessage(change.error)}</div>
      )}

      {t.stages.map((stage) => (
        <div className={`stage ${stage.status}`} key={stage.id}>
          <div className="task-card-top">
            <strong>
              {stage.position}. {stage.title}
            </strong>
            <span>
              {stage.is_overdue && <span className="badge overdue">Overdue</span>}
              <span className={`badge status-${stage.status}`}>
                {statusLabel(stage.status)}
              </span>
            </span>
          </div>

          <div className="muted">
            Step {stage.step}
            {stage.parallel_with_previous ? ' (runs with the previous stage)' : ''}
            {stage.due_date ? ` · due ${formatDateTime(stage.due_date)}` : ''}
          </div>

          <div>
            {stage.tag && <span className="chip">{stage.tag.name}</span>}
            {stage.assignees.length > 0 ? (
              <span>{stage.assignees.map((a) => a.name).join(', ')}</span>
            ) : (
              !stage.tag && <span className="muted">Unassigned</span>
            )}
          </div>

          {stage.status === 'blocked' && stage.blocked_reason && (
            <div className="form-error">Blocked: {stage.blocked_reason}</div>
          )}

          {stage.status === 'done' && stage.completed_at && (
            <div className="muted">
              Completed {formatDateTime(stage.completed_at)}
              {stage.completed_by ? ` by ${stage.completed_by.name}` : ''}
            </div>
          )}

          {stage.allowed_statuses.length > 0 && (
            <div className="actions">
              {stage.allowed_statuses.map((target) => (
                <button
                  key={target}
                  disabled={change.isPending}
                  onClick={() => handleAction(stage, target)}
                >
                  {actionLabel(stage.status, target)}
                </button>
              ))}
            </div>
          )}

          {blockingId === stage.id && (
            <form className="inline-form" onSubmit={handleBlockSubmit}>
              <input
                aria-label="Reason for blocking"
                placeholder="Why is this blocked?"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={300}
                required
              />
              <button type="submit" disabled={change.isPending}>
                Confirm
              </button>
              <button type="button" onClick={() => setBlockingId(null)}>
                Cancel
              </button>
            </form>
          )}
        </div>
      ))}
    </div>
  )
}
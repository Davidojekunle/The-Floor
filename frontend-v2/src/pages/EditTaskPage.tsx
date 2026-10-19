import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { getTask } from '../api/tasks'
import { Icon } from '../components/Icon'
import { useToast } from '../components/toastContext'
import { useTimezone } from '../lib/useTimezone'
import { useRoom } from '../room/roomContext'
import { TaskForm } from '../room/TaskForm'
import { saveTaskChanges } from '../room/saveTaskChanges'
import { draftFromTask, type DraftTask } from '../room/taskDraft'

export function EditTaskPage() {
  const { taskId = '' } = useParams()
  const { room } = useRoom()
  const tz = useTimezone()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()

  const query = useQuery({ queryKey: ['task', room.id, taskId], queryFn: () => getTask(room.id, taskId) })
  const back = `/rooms/${room.id}/tasks/${taskId}`

  if (query.isPending) return <div className="page" />
  if (query.isError)
    return (
      <div className="page">
        <div className="empty">
          <h2>This task didn't load</h2>
          <p>{query.error.message}</p>
        </div>
      </div>
    )

  const original = query.data
  // The server decides: approvers and task creators, or the proposer while the task is a proposal.
  if (!original.can_edit) return <Navigate to={back} replace />
  const isProposal = original.approval_status !== 'approved'

  async function submit(d: DraftTask) {
    const final = await saveTaskChanges(room.id, original, d, tz)
    queryClient.setQueryData(['task', room.id, taskId], final)
    void queryClient.invalidateQueries({ queryKey: ['tasks', room.id] })
    void queryClient.invalidateQueries({ queryKey: ['me-tasks'] })
    toast('Changes saved.')
    navigate(back)
  }

  return (
    <div className="page">
      <div>
        <Link className="back" to={back}>
          <Icon name="back" />
          {original.title}
        </Link>
      </div>
      <div className="page-head">
        <div>
          <h1>{isProposal ? 'Edit proposal' : 'Edit task'}</h1>
          <p className="sub">
            {isProposal
              ? 'Changes are saved to the proposal straight away.'
              : 'Started and finished stages keep their status when you reorder.'}
          </p>
        </div>
      </div>
      {/* key: start fresh if the task changes underneath us */}
      <TaskForm
        key={original.updated_at}
        initial={draftFromTask(original, tz)}
        submitLabel="Save changes"
        pendingLabel="Saving…"
        cancelHref={back}
        onSubmit={submit}
      />
    </div>
  )
}

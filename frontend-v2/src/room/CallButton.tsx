import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { callErrorText, startCall, type LiveCall } from '../api/calls'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { useToast } from '../components/toastContext'
import { useCan, useRoom } from './roomContext'

/**
 * "Start a call", or "Join call · 3" while one is live. In a room (no taskId) the live call comes from /me;
 * on a task, pass the task's live_call. Hidden while calls are switched off.
 */
export function CallButton(props: { taskId?: string; live?: LiveCall | null; className?: string }) {
  const { room } = useRoom()
  const { user } = useAuth()
  const canStart = useCan('call.start')
  const navigate = useNavigate()
  const toast = useToast()
  const live = props.taskId ? props.live : user?.rooms.find((r) => r.id === room.id)?.live_call
  const start = useMutation({
    mutationFn: () => startCall(room.id, props.taskId),
    onSuccess: (call) => navigate(`/rooms/${room.id}/calls/${call.id}`),
    onError: (e) => toast(callErrorText(e instanceof ApiError ? e.code : undefined, "Couldn't start the call. Try again.")),
  })
  if (!user?.calls_enabled) return null

  const cls = `btn ${props.className ?? ''}`.trim()
  if (live)
    return (
      <Link className={`${cls} call-live-btn`} to={`/rooms/${room.id}/calls/${live.id}`}>
        <span className="live-dot" aria-hidden="true" />
        {live.participant_count > 0 ? `Join call · ${live.participant_count}` : 'Join call'}
      </Link>
    )
  if (!canStart) return null
  return (
    <button className={cls} type="button" disabled={start.isPending} onClick={() => start.mutate()}>
      <Icon name="video" />
      {start.isPending ? 'Starting…' : props.taskId ? 'Call about this task' : 'Start a call'}
    </button>
  )
}

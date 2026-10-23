import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getJoinPreview, requestToJoin } from '../api/rooms'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { Logo } from '../components/Logo'
import { plural } from '../lib/labels'

export function JoinPage() {
  const { code = '' } = useParams()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { refreshUser } = useAuth()

  const preview = useQuery({
    queryKey: ['join-preview', code],
    queryFn: () => getJoinPreview(code),
    retry: false,
  })

  const join = useMutation({
    mutationFn: () => requestToJoin(code),
    onSuccess: async (m) => {
      if (m.status !== 'active') return // asked to join: the refreshed preview says so
      await refreshUser().catch(() => {}) // invited: straight in, so the room is in the list
      navigate(`/rooms/${m.room_id}`, { replace: true })
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['join-preview', code] }),
  })

  let body
  if (preview.isPending) {
    body = <p className="muted">Loading the invitation…</p>
  } else if (preview.isError) {
    const invalid = preview.error instanceof ApiError && preview.error.code === 'NOT_FOUND'
    body = (
      <>
        <span className="room-sq lg muted-sq">
          <Icon name="link" size={20} />
        </span>
        <div className="invite-head">
          <h1>{invalid ? 'This link no longer works' : "This invitation didn't load"}</h1>
          <p className="muted">
            {invalid
              ? "The room's head may have made a new one. Ask them to send you the current link."
              : preview.error.message}
          </p>
        </div>
        <Link className="btn block" to="/rooms">
          Go to your rooms
        </Link>
      </>
    )
  } else {
    const { room_name, member_count, already_member, already_requested, invited } = preview.data
    // A conflict means our view was stale; the refreshed preview shows the right state.
    const joinError =
      join.error instanceof ApiError && !['ALREADY_MEMBER', 'ALREADY_REQUESTED'].includes(join.error.code)
        ? join.error.message
        : null
    body = (
      <>
        <span className="room-sq lg">{room_name[0]}</span>
        <div className="invite-head">
          <p className="eyebrow">You're invited to join</p>
          <h1>{room_name}</h1>
          <p className="muted">{plural(member_count, 'member')}</p>
        </div>
        {joinError && (
          <div className="form-error" role="alert">
            {joinError}
          </div>
        )}
        {already_member ? (
          <>
            <p className="muted">You're already a member of this room.</p>
            <Link className="btn primary block" to="/rooms">
              Go to your rooms
            </Link>
          </>
        ) : already_requested ? (
          <>
            <div className="waiting">
              <strong>
                <span className="pulse" />
                Request sent
              </strong>
              <span className="muted small">
                The head of {room_name} will review it. Once you're in, the room shows up in your rooms list.
              </span>
            </div>
            <Link className="btn block" to="/rooms">
              Go to your rooms
            </Link>
          </>
        ) : (
          <>
            <button className="btn primary block" type="button" onClick={() => join.mutate()} disabled={join.isPending}>
              {invited ? (join.isPending ? 'Joining…' : `Join ${room_name}`) : join.isPending ? 'Sending…' : 'Ask to join'}
            </button>
            <p className="faint small">
              {invited ? "You were invited by email, so you're let straight in." : 'The head approves everyone who joins.'}
            </p>
          </>
        )}
      </>
    )
  }

  return (
    <div className="center-screen">
      <div className="auth" style={{ width: 'min(420px, 100%)' }}>
        <Logo />
        <div className="invite">{body}</div>
      </div>
    </div>
  )
}

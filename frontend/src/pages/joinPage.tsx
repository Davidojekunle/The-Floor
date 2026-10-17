import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getJoinPreview, requestToJoin } from '../api/room'

export function JoinPage() {
  const { code = '' } = useParams()
  const queryClient = useQueryClient()

  const preview = useQuery({
    queryKey: ['join-preview', code],
    queryFn: () => getJoinPreview(code),
    retry: false,
  })

  const join = useMutation({
    mutationFn: () => requestToJoin(code),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['join-preview', code] }),
  })

  if (preview.isPending) return <p className="page">Loading...</p>

  if (preview.isError) {
    const notFound =
      preview.error instanceof ApiError && preview.error.status === 404
    return (
      <div className="auth-page">
        <div className="card">
          <h1>{notFound ? 'Invite link not valid' : 'Something went wrong'}</h1>
          <p>
            {notFound
              ? 'This link is invalid or has been replaced. Ask the head of the room for a new one.'
              : preview.error.message}
          </p>
          <Link to="/rooms">Back to my rooms</Link>
        </div>
      </div>
    )
  }

  const { room_name, member_count, already_member, already_requested } =
    preview.data

  return (
    <div className="auth-page">
      <div className="card">
        <h1>{room_name}</h1>
        <p>{member_count} members</p>

        {join.error && (
          <div className="form-error">
            {join.error instanceof ApiError
              ? join.error.message
              : 'Something went wrong.'}
          </div>
        )}

        {already_member ? (
          <p>You are already a member of this room.</p>
        ) : already_requested ? (
          <p>Your request was sent. Waiting for the head to approve you.</p>
        ) : (
          <button
            className="primary"
            onClick={() => join.mutate()}
            disabled={join.isPending}
          >
            {join.isPending ? 'Sending...' : 'Request to join'}
          </button>
        )}

        <p className="switch-link">
          <Link to="/rooms">Back to my rooms</Link>
        </p>
      </div>
    </div>
  )
}
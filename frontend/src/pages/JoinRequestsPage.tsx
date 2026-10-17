import { useState } from 'react'
import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { ApiError } from '../api/client'
import {
  approveJoinRequest,
  listJoinRequests,
  rejectJoinRequest,
} from '../api/room'
import { useAuth } from '../auth/useAuth'
import { useCan, useRoom } from '../room/useRoom'

export function JoinRequestsPage() {
  const { room, refreshRoom } = useRoom()
  const { refreshUser } = useAuth()
  const canManage = useCan('join.manage')
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)

  const requests = useQuery({
    queryKey: ['join-requests', room.id, page],
    queryFn: () => listJoinRequests(room.id, page),
    enabled: canManage,
  })

  const decide = useMutation({
    mutationFn: (vars: {
      membershipId: string
      action: 'approve' | 'reject'
    }) =>
      vars.action === 'approve'
        ? approveJoinRequest(room.id, vars.membershipId)
        : rejectJoinRequest(room.id, vars.membershipId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['join-requests', room.id],
      })
      await refreshUser()
    },
    onError: (err) => {
      // 403 means our permissions may be out of date
      if (err instanceof ApiError && err.status === 403) refreshRoom()
    },
  })

  if (!canManage) return <p>You don't have access to join requests.</p>
  if (requests.isPending) return <p>Loading...</p>
  if (requests.isError) return <p>Could not load join requests.</p>

  const { items, total, limit } = requests.data
  const totalPages = Math.max(1, Math.ceil(total / limit))

  return (
    <div>
      <h1>Join requests</h1>

      {decide.error && (
        <div className="form-error">
          {decide.error instanceof ApiError
            ? decide.error.message
            : 'Something went wrong.'}
        </div>
      )}

      {items.length === 0 ? (
        <p>No pending requests.</p>
      ) : (
        items.map((item) => (
          <div className="row" key={item.membership_id}>
            <div>
              <strong>{item.user.name}</strong>
              <div>
                requested {new Date(item.requested_at).toLocaleString()}
              </div>
            </div>
            <div className="actions">
              <button
                disabled={decide.isPending}
                onClick={() =>
                  decide.mutate({
                    membershipId: item.membership_id,
                    action: 'approve',
                  })
                }
              >
                Approve
              </button>
              <button
                disabled={decide.isPending}
                onClick={() =>
                  decide.mutate({
                    membershipId: item.membership_id,
                    action: 'reject',
                  })
                }
              >
                Reject
              </button>
            </div>
          </div>
        ))
      )}

      {totalPages > 1 && (
        <p>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>{' '}
          Page {page} of {totalPages}{' '}
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </p>
      )}
    </div>
  )
}
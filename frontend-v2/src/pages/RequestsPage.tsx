import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { approveJoinRequest, listJoinRequests, rejectJoinRequest, type JoinRequestItem } from '../api/rooms'
import { listTasks } from '../api/tasks'
import { useAuth } from '../auth/useAuth'
import { Avatar } from '../components/Avatar'
import { ConfirmDialog } from '../components/Dialog'
import { useToast } from '../components/toastContext'
import { relativeTime } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'
import { ProposalRow } from '../room/ProposalRow'
import { useCan, useRoom } from '../room/roomContext'
import { useRoomError } from '../room/useRoomError'

/** Everything in the room waiting on my decision: people asking to join, and proposed tasks. */
export function RequestsPage() {
  const { room } = useRoom()
  const canJoins = useCan('join.manage')
  const canApprove = useCan('task.approve')

  if (!canJoins && !canApprove) return <Navigate to={`/rooms/${room.id}`} replace />

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Requests</h1>
          <p className="sub">Things in {room.name} waiting for your decision.</p>
        </div>
      </div>
      {canJoins && <JoinRequests />}
      {canApprove && <Proposals />}
    </div>
  )
}

function Proposals() {
  const { room } = useRoom()
  const pending = useQuery({
    queryKey: ['tasks', room.id, 'proposals', 'pending'],
    queryFn: () => listTasks(room.id, { approval_status: 'pending', sort: 'submitted_at' }),
  })
  const rejected = useQuery({
    queryKey: ['tasks', room.id, 'proposals', 'rejected'],
    queryFn: () => listTasks(room.id, { approval_status: 'rejected', sort: 'submitted_at' }),
  })
  const lastRejected = rejected.data?.items.at(-1)

  return (
    <section className="section">
      <div className="section-h">
        <h2>Tasks</h2>
        <span className="faint small">Proposed by members, oldest first</span>
      </div>
      <div className="list">
        {pending.isPending ? (
          <div className="empty" style={{ padding: 24 }}>
            <p>Loading proposals…</p>
          </div>
        ) : !pending.data?.items.length ? (
          <div className="empty" style={{ padding: 24 }}>
            <p>No tasks are waiting for approval.</p>
          </div>
        ) : (
          pending.data.items.map((t) => (
            <ProposalRow key={t.id} task={t} mode="review" href={`/rooms/${room.id}/tasks/${t.id}`} />
          ))
        )}
      </div>
      {lastRejected && (
        <p className="faint small">
          {rejected.data!.total === 1 ? '1 proposal was' : `${rejected.data!.total} proposals were`} not approved.{' '}
          <Link to={`/rooms/${room.id}/tasks/${lastRejected.id}`}>
            See {rejected.data!.total === 1 ? 'it' : 'the latest'}
          </Link>
        </p>
      )}
    </section>
  )
}

function JoinRequests() {
  const { room, refreshRoom } = useRoom()
  const { refreshUser } = useAuth()
  const tz = useTimezone()
  const queryClient = useQueryClient()
  const toast = useToast()
  const onError = useRoomError()
  const [page, setPage] = useState(1)
  const [declining, setDeclining] = useState<JoinRequestItem | null>(null)

  const requests = useQuery({
    queryKey: ['join-requests', room.id, page],
    queryFn: () => listJoinRequests(room.id, page),
  })

  const afterDecision = async () => {
    await queryClient.invalidateQueries({ queryKey: ['join-requests', room.id] })
    void queryClient.invalidateQueries({ queryKey: ['members', room.id] })
    refreshRoom()
    await refreshUser() // updates the Requests badge
  }

  const decide = useMutation({
    mutationFn: (v: { item: JoinRequestItem; approve: boolean }) =>
      v.approve ? approveJoinRequest(room.id, v.item.membership_id) : rejectJoinRequest(room.id, v.item.membership_id),
    onSuccess: async (_, v) => {
      setDeclining(null)
      // If that was the last request on a later page, step back a page.
      if (page > 1 && requests.data?.items.length === 1) setPage(page - 1)
      await afterDecision()
      toast(v.approve ? `${v.item.user.name} joined ${room.name}.` : `Declined ${v.item.user.name}'s request.`)
    },
    onError: async (err) => {
      setDeclining(null)
      if (err instanceof ApiError && err.code === 'REQUEST_NOT_PENDING') {
        toast('Someone already handled this request.')
        await afterDecision()
      } else toast(onError(err))
    },
  })

  const data = requests.data
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.limit)) : 1

  return (
    <section className="section">
      <div className="section-h">
        <h2>People</h2>
        <span className="faint small">Asked to join with your invite link</span>
      </div>
      <div className="list">
        {requests.isPending ? (
          <div className="empty" style={{ padding: 24 }}>
            <p>Loading requests…</p>
          </div>
        ) : requests.isError ? (
          <div className="empty" style={{ padding: 24 }}>
            <p>Requests didn't load.</p>
            <button className="btn sm" type="button" onClick={() => void requests.refetch()}>
              Try again
            </button>
          </div>
        ) : data!.items.length === 0 ? (
          <div className="empty" style={{ padding: 24 }}>
            <p>No one is waiting to join.</p>
            {room.invite_code && (
              <Link className="btn sm" to={`/rooms/${room.id}/settings`} style={{ marginTop: 8 }}>
                Get the invite link
              </Link>
            )}
          </div>
        ) : (
          data!.items.map((item) => (
            <div className="row decide-row" key={item.membership_id}>
              <Avatar name={item.user.name} />
              <div className="main">
                <div className="title">{item.user.name}</div>
                <div className="meta" title={new Date(item.requested_at).toLocaleString()}>
                  Asked {relativeTime(item.requested_at, tz)}
                </div>
              </div>
              <div className="end">
                <button className="btn ghost sm" type="button" disabled={decide.isPending} onClick={() => setDeclining(item)}>
                  Decline
                </button>
                <button
                  className="btn primary sm"
                  type="button"
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ item, approve: true })}
                >
                  Approve
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {totalPages > 1 && (
        <div className="pager">
          <button className="btn sm" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span className="muted small">
            Page {page} of {totalPages}
          </span>
          <button className="btn sm" type="button" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            Next
          </button>
        </div>
      )}

      {declining && (
        <ConfirmDialog
          title={`Decline ${declining.user.name}?`}
          body="They won't be added to the room. They can ask again later with the same link."
          confirmLabel="Decline"
          pending={decide.isPending}
          onConfirm={() => decide.mutate({ item: declining, approve: false })}
          onClose={() => setDeclining(null)}
        />
      )}
    </section>
  )
}

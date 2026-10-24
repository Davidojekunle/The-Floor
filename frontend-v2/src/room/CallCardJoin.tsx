import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getCall } from '../api/calls'
import { useRoom } from './roomContext'

const MAX_HOURS = 3 // a call never runs longer, so older cards don't ask

/** On a "started a call" chat card: Join while that call is still live. */
export function CallCardJoin({ callId, at }: { callId: string; at: string }) {
  const { room } = useRoom()
  const [now] = useState(() => Date.now()) // when the card first showed: good enough to skip long-finished calls
  const recent = now - new Date(at).getTime() < MAX_HOURS * 3600_000
  const call = useQuery({
    queryKey: ['call', room.id, callId],
    queryFn: () => getCall(room.id, callId),
    enabled: recent,
    retry: false,
  })
  if (!recent || call.data?.status !== 'live') return null
  return (
    <>
      {' · '}
      <Link className="sys-link" to={`/rooms/${room.id}/calls/${callId}`}>
        Join
      </Link>
    </>
  )
}

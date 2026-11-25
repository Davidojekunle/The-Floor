import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { answerMeeting, type Call } from '../api/calls'
import { useToast } from '../components/toastContext'
import { useRoom } from './roomContext'

/** On a coming meeting: who's going, who can't, and (for invitees) Going / Can't make it. */
export function RsvpBox({ call: c }: { call: Call }) {
  const { room } = useRoom()
  const toast = useToast()
  const queryClient = useQueryClient()
  const answer = useMutation({
    mutationFn: (r: 'going' | 'declined' | null) => answerMeeting(room.id, c.id, r),
    onSuccess: (call) => {
      queryClient.setQueryData(['call', room.id, c.id], call)
      void queryClient.invalidateQueries({ queryKey: ['calls', room.id] })
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : "Couldn't save your answer. Try again."),
  })
  const r = c.rsvp
  if (!r) return null
  const names = (list: { name: string }[]) => list.map((p) => p.name).join(', ')
  return (
    <div className="rsvp">
      {r.invited && (
        <div className="seg" role="radiogroup" aria-label="Are you going?">
          <button type="button" role="radio" aria-checked={r.mine === 'going'} disabled={answer.isPending}
            onClick={() => answer.mutate(r.mine === 'going' ? null : 'going')}>
            Going
          </button>
          <button type="button" role="radio" aria-checked={r.mine === 'declined'} disabled={answer.isPending}
            onClick={() => answer.mutate(r.mine === 'declined' ? null : 'declined')}>
            Can't make it
          </button>
        </div>
      )}
      {(r.going.length > 0 || r.declined.length > 0) && (
        <p className="faint small">
          {r.going.length > 0 && <>Going: {names(r.going)}</>}
          {r.going.length > 0 && r.declined.length > 0 && ' · '}
          {r.declined.length > 0 && <>Can't make it: {names(r.declined)}</>}
        </p>
      )}
    </div>
  )
}

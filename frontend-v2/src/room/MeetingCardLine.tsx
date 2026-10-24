import { dayAndTime } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'

/** On a meeting chat card: when it is, in the reader's own timezone. */
export function MeetingCardLine({ detail }: { detail: { starts_at: string; repeat?: string | null } }) {
  const tz = useTimezone()
  return (
    <>
      {' · '}
      {dayAndTime(detail.starts_at, tz)}
      {detail.repeat ? `, ${detail.repeat}` : ''}
    </>
  )
}

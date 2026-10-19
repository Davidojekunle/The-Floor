import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { setTempHead, type Member } from '../api/members'
import { Dialog } from '../components/Dialog'
import { useToast } from '../components/toastContext'
import { dayInput, dayKey, endOfDayIso, formatDay } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'
import { useRoom } from './roomContext'
import { useRoomError } from './useRoomError'

const MAX_DAYS = 90 // the server allows up to the end of the 90th day from today, in the head's timezone

/** Make a member a temporary head, or change when an existing grant ends (the same PUT). */
export function TempHeadDialog({ member, onClose, onSaved }: { member: Member; onClose: () => void; onSaved: () => void }) {
  const { room } = useRoom()
  const tz = useTimezone()
  const toast = useToast()
  const onError = useRoomError()
  const changing = !!member.temp_head_expires_at
  const first = member.user.name.split(' ')[0]

  const [day, setDay] = useState(() => (member.temp_head_expires_at ? dayKey(member.temp_head_expires_at, tz) : dayInput(tz, 7)))
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: () => setTempHead(room.id, member.membership_id, endOfDayIso(day, tz)),
    onSuccess: (updated) => {
      onSaved()
      onClose()
      const until = updated.temp_head_expires_at ? formatDay(updated.temp_head_expires_at, tz) : formatDay(endOfDayIso(day, tz), tz)
      toast(changing ? `${first}'s temporary head role now ends ${until}.` : `${first} is a temporary head until ${until}.`)
    },
    onError: (err) => {
      if (err instanceof ApiError && err.fields?.expires_at) setError(err.fields.expires_at)
      else if (err instanceof ApiError && err.code === 'ALREADY_HEAD') setError(`${first} is the head of this room.`)
      else setError(onError(err))
    },
  })

  const presets: [string, number][] = [
    ['1 week', 7],
    ['2 weeks', 14],
    ['30 days', 30],
  ]

  return (
    <Dialog
      title={changing ? `Change when ${first}'s role ends` : `Make ${first} a temporary head`}
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" disabled={save.isPending || !day} onClick={() => save.mutate()}>
            {changing ? 'Save' : 'Make temporary head'}
          </button>
        </>
      }
    >
      {!changing && (
        <p className="muted small">
          Until the end date, {first} can create, approve and assign tasks in {room.name}. They can't manage join requests, tags or
          members. Everything they do stays after the role ends.
        </p>
      )}
      <div className="field">
        <label htmlFor="th-until">Ends at the end of</label>
        <div className="seg" role="group" aria-label="Quick choices" style={{ justifySelf: 'start' }}>
          {presets.map(([label, n]) => {
            const d = dayInput(tz, n)
            return (
              <button key={n} type="button" aria-pressed={day === d} onClick={() => (setDay(d), setError(null))}>
                {label}
              </button>
            )
          })}
        </div>
        <input
          className="input"
          type="date"
          id="th-until"
          value={day}
          min={dayInput(tz)}
          max={dayInput(tz, MAX_DAYS)}
          onChange={(e) => {
            setDay(e.target.value)
            setError(null)
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby="th-until-hint"
        />
        <span className={error ? 'err' : 'hint'} id="th-until-hint" role={error ? 'alert' : undefined}>
          {error ?? (day ? `${formatDay(endOfDayIso(day, tz), tz)}, 23:59 (${tz.replace(/_/g, ' ')} time). Up to ${MAX_DAYS} days.` : `Up to ${MAX_DAYS} days.`)}
        </span>
      </div>
    </Dialog>
  )
}

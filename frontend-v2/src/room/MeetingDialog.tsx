import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { checkClashes, scheduleMeeting, updateMeeting, type Call, type Clash, type InviteIn } from '../api/calls'
import { listMembers, listTags } from '../api/members'
import { useAuth } from '../auth/useAuth'
import { Dialog } from '../components/Dialog'
import { useToast } from '../components/toastContext'
import { addDays, atTimeIso, dayAndTime, dayInput, dayKey, timeOfDay } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'
import { useRoom } from './roomContext'

const LENGTHS = [15, 30, 45, 60, 90, 120, 180]
type Who = 'everyone' | 'some'
type Repeat = 'none' | 'week' | '2weeks'

/** Schedule a meeting (or change one). Heads and temp heads. Times are in the user's profile timezone. */
export function MeetingDialog(props: { onClose: () => void; task?: { id: string; title: string }; meeting?: Call }) {
  const { room } = useRoom()
  const { user } = useAuth()
  const tz = useTimezone()
  const toast = useToast()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const m = props.meeting
  const editing = !!m

  const [title, setTitle] = useState(m?.title ?? (props.task ? `About ${props.task.title}` : ''))
  const [description, setDescription] = useState(m?.description ?? '')
  const [day, setDay] = useState(m?.starts_at ? dayKey(m.starts_at, tz) : dayInput(tz, 1))
  const [time, setTime] = useState(m?.starts_at ? timeOfDay(m.starts_at, tz) : '10:00')
  const [length, setLength] = useState(m?.duration_minutes ?? 45)
  const [who, setWho] = useState<Who>(m?.invite && !m.invite.everyone ? 'some' : 'everyone')
  const [people, setPeople] = useState<string[]>(m?.invite?.users.map((u) => u.id) ?? [])
  const [tags, setTags] = useState<string[]>(m?.invite?.tags.map((t) => t.id) ?? [])
  const [where, setWhere] = useState<'app' | 'link'>(m?.external_url ? 'link' : 'app')
  const [link, setLink] = useState(m?.external_url ?? '')
  const [repeat, setRepeat] = useState<Repeat>('none')
  const [until, setUntil] = useState(addDays(dayInput(tz, 1), 28))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [clashes, setClashes] = useState<Clash[]>([])

  const members = useQuery({ queryKey: ['members', room.id], queryFn: () => listMembers(room.id) })
  const roomTags = useQuery({ queryKey: ['tags', room.id], queryFn: () => listTags(room.id) })

  const invite: InviteIn = { everyone: who === 'everyone', user_ids: who === 'some' ? people : [], tag_ids: who === 'some' ? tags : [] }
  const startsAt = day && /^\d\d:\d\d$/.test(time) ? atTimeIso(day, time, tz) : null
  const inviteKey = JSON.stringify(invite)

  // The clash note: who already has a meeting then. Checked after the form settles, never blocks.
  useEffect(() => {
    if (!startsAt || (!invite.everyone && !people.length && !tags.length)) return
    const t = setTimeout(() => {
      checkClashes(room.id, { starts_at: startsAt, duration_minutes: length, invite, exclude_call_id: m?.id })
        .then((r) => setClashes(r.clashes))
        .catch(() => setClashes([]))
    }, 400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- invite is compared by inviteKey
  }, [startsAt, length, inviteKey, room.id, m?.id])

  const save = useMutation({
    mutationFn: () => {
      const body = {
        title: title.trim(),
        description: description.trim() || null,
        starts_at: startsAt!,
        duration_minutes: length,
        invite,
        external_url: where === 'link' ? link.trim() : null,
        ...(props.task && !editing ? { task_id: props.task.id } : {}),
      }
      return editing
        ? updateMeeting(room.id, m.id, body)
        : scheduleMeeting(room.id, { ...body, repeat: repeat === 'none' ? null : { every: repeat, until } })
    },
    onSuccess: (call) => {
      void queryClient.invalidateQueries({ queryKey: ['calls', room.id] })
      void queryClient.invalidateQueries({ queryKey: ['call', room.id, call.id] })
      toast(editing ? 'Meeting updated. Invitees are told.' : `${call.title} is scheduled. Invitees are told.`)
      props.onClose()
      if (!editing) navigate(`/rooms/${room.id}/calls/${call.id}`)
    },
    onError: (e) => {
      if (e instanceof ApiError && e.fields) {
        const f = e.fields
        setErrors({
          title: f.title ?? '',
          starts_at: f.starts_at ?? '',
          invite: f.invite ?? f['invite.user_ids'] ?? f['invite.tag_ids'] ?? '',
          external_url: f.external_url ?? '',
          until: f['repeat.until'] ?? '',
        })
      } else toast(e instanceof ApiError ? e.message : "Couldn't save the meeting. Try again.")
    },
  })

  const submit = () => {
    const local: Record<string, string> = {}
    if (!title.trim()) local.title = 'Give the meeting a name.'
    if (!startsAt) local.starts_at = 'Pick a day and a time.'
    else if (new Date(startsAt) <= new Date()) local.starts_at = 'Pick a time in the future.'
    if (who === 'some' && !people.length && !tags.length) local.invite = 'Pick at least one person or tag.'
    if (where === 'link' && !/^https:\/\//.test(link.trim())) local.external_url = 'Paste a full link starting with https://'
    setErrors(local)
    if (!Object.values(local).some(Boolean)) save.mutate()
  }

  const toggle = (list: string[], set: (v: string[]) => void, id: string) =>
    set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
  const err = (k: string) =>
    errors[k] ? (
      <span className="err" role="alert">
        {errors[k]}
      </span>
    ) : null

  return (
    <Dialog
      title={editing ? 'Change the meeting' : props.task ? `Schedule a meeting about ${props.task.title}` : 'Schedule a meeting'}
      onClose={props.onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={props.onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" disabled={save.isPending} onClick={submit}>
            {save.isPending ? 'Saving…' : editing ? 'Save changes' : 'Schedule'}
          </button>
        </>
      }
    >
      <form
        className="meeting-form"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <div className="field">
          <label htmlFor="mt-title">Name</label>
          <input className="input" id="mt-title" maxLength={100} placeholder="e.g. Weekly review" value={title}
            onChange={(e) => setTitle(e.target.value)} aria-invalid={errors.title ? true : undefined} />
          {err('title')}
        </div>

        <div className="three">
          <div className="field">
            <label htmlFor="mt-day">Day</label>
            <input className="input" id="mt-day" type="date" value={day} min={dayInput(tz)} onChange={(e) => setDay(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="mt-time">Time</label>
            <input className="input" id="mt-time" type="time" step={300} value={time} onChange={(e) => setTime(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="mt-len">Length</label>
            <select className="select" id="mt-len" value={length} onChange={(e) => setLength(Number(e.target.value))}>
              {LENGTHS.map((n) => (
                <option key={n} value={n}>
                  {n < 60 ? `${n} min` : `${n / 60} h${n % 60 ? ` ${n % 60} min` : ''}`}
                </option>
              ))}
            </select>
          </div>
        </div>
        {err('starts_at') ?? <span className="hint">{tz.replace(/_/g, ' ')} time. Everyone sees it in their own.</span>}

        {!editing && (
          <div className="two">
            <div className="field">
              <label htmlFor="mt-repeat">Repeat</label>
              <select className="select" id="mt-repeat" value={repeat} onChange={(e) => setRepeat(e.target.value as Repeat)}>
                <option value="none">Doesn't repeat</option>
                <option value="week">Every week</option>
                <option value="2weeks">Every two weeks</option>
              </select>
            </div>
            {repeat !== 'none' && (
              <div className="field">
                <label htmlFor="mt-until">Until</label>
                <input className="input" id="mt-until" type="date" value={until} min={day} onChange={(e) => setUntil(e.target.value)} />
                {err('until')}
              </div>
            )}
          </div>
        )}

        <fieldset className="field">
          <legend>Who's invited</legend>
          <div className="seg" role="radiogroup" aria-label="Who's invited">
            <button type="button" role="radio" aria-checked={who === 'everyone'} onClick={() => setWho('everyone')}>
              Everyone in {room.name}
            </button>
            <button type="button" role="radio" aria-checked={who === 'some'} onClick={() => setWho('some')}>
              Choose people or tags
            </button>
          </div>
          {who === 'some' && (
            <div className="pick-list">
              {(roomTags.data?.items ?? []).map((t) => (
                <label className="check" key={t.id}>
                  <input type="checkbox" checked={tags.includes(t.id)} onChange={() => toggle(tags, setTags, t.id)} />
                  Everyone tagged {t.name}
                </label>
              ))}
              {(members.data?.items ?? [])
                .filter((p) => p.user.id !== user?.id)
                .map((p) => (
                  <label className="check" key={p.user.id}>
                    <input type="checkbox" checked={people.includes(p.user.id)} onChange={() => toggle(people, setPeople, p.user.id)} />
                    {p.user.name}
                  </label>
                ))}
            </div>
          )}
          {err('invite')}
        </fieldset>

        {clashes.length > 0 && (
          <div className="clash-note" role="status">
            <strong>Heads up:</strong>
            <ul>
              {clashes.slice(0, 4).map((c, i) => (
                <li key={i}>
                  {c.user.name} has {c.title} then ({dayAndTime(c.starts_at, tz)}
                  {c.room_name !== room.name ? `, ${c.room_name}` : ''})
                </li>
              ))}
            </ul>
            {clashes.length > 4 && <span className="faint small">and {clashes.length - 4} more</span>}
          </div>
        )}

        <fieldset className="field">
          <legend>Where</legend>
          <div className="seg" role="radiogroup" aria-label="Where">
            <button type="button" role="radio" aria-checked={where === 'app'} onClick={() => setWhere('app')}>
              A call in The Floor
            </button>
            <button type="button" role="radio" aria-checked={where === 'link'} onClick={() => setWhere('link')}>
              Google Meet or Zoom link
            </button>
          </div>
          {where === 'link' && (
            <>
              <input className="input" type="url" inputMode="url" placeholder="https://meet.google.com/…" value={link}
                onChange={(e) => setLink(e.target.value)} aria-label="Meeting link" aria-invalid={errors.external_url ? true : undefined} />
              {err('external_url')}
            </>
          )}
        </fieldset>

        <div className="field">
          <label htmlFor="mt-desc">
            Notes <span className="faint" style={{ fontWeight: 400 }}>(optional)</span>
          </label>
          <textarea className="textarea" id="mt-desc" rows={3} maxLength={1000} placeholder="What it's about"
            value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <button type="submit" hidden />
      </form>
    </Dialog>
  )
}

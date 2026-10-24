import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LiveKitRoom, VideoConference } from '@livekit/components-react'
import '@livekit/components-styles'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { callErrorText, cancelMeeting, endCall, getCall, joinCall, type Call, type JoinPass } from '../api/calls'
import { Avatar } from '../components/Avatar'
import { ConfirmDialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { Switch } from '../components/Switch'
import { useToast } from '../components/toastContext'
import { useRoom } from '../room/roomContext'
import { MeetingDialog } from '../room/MeetingDialog'
import { dayAndTime, timeOfDay } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'

type Phase = 'ready' | 'joining' | 'in' | 'left' | 'error'
type LivekitPass = Extract<JoinPass, { provider: 'livekit' }>

/** A call: LiveKit's ready-made conference screen, with who's in and "End for everyone" above it. */
export function CallPage() {
  const { callId = '' } = useParams()
  const { room } = useRoom()
  const toast = useToast()
  const queryClient = useQueryClient()
  const [phase, setPhase] = useState<Phase>('ready')
  const [pass, setPass] = useState<LivekitPass>()
  const [editing, setEditing] = useState(false)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const tz = useTimezone()
  const [now, setNow] = useState(() => Date.now()) // ticks, so Join appears by itself 10 minutes before
  useEffect(() => {
    const i = setInterval(() => setNow(Date.now()), 15_000)
    return () => clearInterval(i)
  }, [])
  const [error, setError] = useState<string>()
  const [camera, setCamera] = useState(true)
  const [mic, setMic] = useState(true)
  const [confirmEnd, setConfirmEnd] = useState(false)

  const call = useQuery({ queryKey: ['call', room.id, callId], queryFn: () => getCall(room.id, callId), retry: false })
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['call', room.id, callId] })

  const join = async () => {
    setPhase('joining')
    setError(undefined)
    try {
      const p = await joinCall(room.id, callId)
      if (p.provider === 'link') {
        window.open(p.url, '_blank', 'noopener')
        setPhase('ready')
        toast('The meeting opened in a new tab.')
        return
      }
      setPass(p)
      setPhase('in')
      refresh() // a meeting goes live with its first join
    } catch (e) {
      setPhase('error')
      const code = e instanceof ApiError ? e.code : undefined
      setError(code === 'CALL_NOT_OPEN' && e instanceof ApiError
        ? e.message
        : callErrorText(code, "Couldn't join the call. Check your connection and try again."))
    }
  }

  const cancel = useMutation({
    mutationFn: (following: boolean) => cancelMeeting(room.id, callId, following),
    onSuccess: () => {
      setConfirmCancel(false)
      toast('Meeting cancelled. Invitees are told.')
      refresh()
      void queryClient.invalidateQueries({ queryKey: ['calls', room.id] })
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : "Couldn't cancel the meeting. Try again."),
  })

  const end = useMutation({
    mutationFn: () => endCall(room.id, callId),
    onSuccess: () => {
      setConfirmEnd(false)
      toast('Call ended for everyone.')
      refresh()
    },
    onError: (e) => toast(callErrorText(e instanceof ApiError ? e.code : undefined, "Couldn't end the call. Try again.")),
  })

  if (call.isPending) return <div className="call-page"><p className="call-note">Loading the call…</p></div>
  if (call.isError)
    return (
      <div className="call-page">
        <div className="empty">
          <h2>This call doesn't exist</h2>
          <p>It may belong to a room you're no longer in.</p>
          <Link className="btn" to={`/rooms/${room.id}`}>Back to {room.name}</Link>
        </div>
      </div>
    )

  const c = call.data
  const home = c.task ? `/rooms/${room.id}/tasks/${c.task.id}` : `/rooms/${room.id}`
  const live = c.status === 'live'
  const scheduled = c.status === 'scheduled'
  const open = scheduled && now >= new Date(c.joinable_from).getTime()
  const connected = (live || scheduled) && phase === 'in' && pass

  return (
    <div className="call-page">
      <header className="call-bar">
        <Link className="btn ghost sm" to={home}>
          <Icon name="back" size={14} />
          {c.task ? c.task.title : room.name}
        </Link>
        <div className="call-title">
          <strong>{c.title}</strong>
          <span className="faint small">
            {live
              ? c.participants.length
                ? `${c.participants.length} in the call`
                : 'Nobody in yet'
              : scheduled && c.starts_at
                ? dayAndTime(c.starts_at, tz)
                : c.status === 'cancelled'
                  ? 'Cancelled'
                  : c.missed
                    ? 'Missed'
                    : 'Ended'}
          </span>
        </div>
        <span className="avstack" aria-label={c.participants.map((p) => p.name).join(', ')}>
          {c.participants.slice(0, 4).map((p) => (
            <Avatar key={p.id} name={p.name} size="sm" />
          ))}
        </span>
        {c.can_edit && scheduled && (
          <>
            <button className="btn sm" type="button" onClick={() => setEditing(true)}>
              Change
            </button>
            <button className="btn danger-outline sm" type="button" onClick={() => setConfirmCancel(true)}>
              Cancel meeting
            </button>
          </>
        )}
        {c.can_end && live && (
          <button className="btn danger-outline sm" type="button" onClick={() => setConfirmEnd(true)}>
            End for everyone
          </button>
        )}
      </header>

      {connected ? (
        <div className="call-frame" data-lk-theme="default">
          <LiveKitRoom
            serverUrl={pass.server_url}
            token={pass.token}
            connect
            video={camera}
            audio={mic}
            onConnected={refresh}
            onDisconnected={() => {
              setPhase('left')
              setPass(undefined)
              refresh()
            }}
            onError={() => {
              setPhase('error')
              setError('The call dropped. Check your connection and try again.')
            }}
            style={{ height: '100%' }}
          >
            <VideoConference />
          </LiveKitRoom>
        </div>
      ) : !live && !scheduled ? (
        <Finished call={c} home={home} />
      ) : scheduled && (!open || c.external_url) && phase !== 'error' ? (
        <MeetingDetails call={c} open={open} onJoin={() => void join()} joining={phase === 'joining'} />
      ) : phase === 'left' ? (
        <div className="empty">
          <h2>You left the call</h2>
          <p>It carries on for everyone else, and ends 2 minutes after the last person leaves.</p>
          <div className="row-actions">
            <button className="btn primary" type="button" onClick={() => void join()}>Rejoin</button>
            <Link className="btn" to={home}>Back</Link>
          </div>
        </div>
      ) : phase === 'error' ? (
        <div className="empty" role="alert">
          <h2>Couldn't join</h2>
          <p>{error}</p>
          <button className="btn primary" type="button" onClick={() => void join()}>Try again</button>
        </div>
      ) : (
        <div className="call-ready">
          <h2>Ready to join?</h2>
          <p className="muted">Your browser asks for the camera and microphone when you join. You can change both in the call.</p>
          <div className="call-ready-switches">
            <Switch label="Camera" checked={camera} onChange={setCamera} />
            <Switch label="Microphone" checked={mic} onChange={setMic} />
          </div>
          <button className="btn primary" type="button" disabled={phase === 'joining'} onClick={() => void join()}>
            <Icon name="video" />
            {phase === 'joining' ? 'Joining…' : 'Join call'}
          </button>
        </div>
      )}

      {editing && <MeetingDialog meeting={c} onClose={() => { setEditing(false); refresh() }} />}
      {confirmCancel && (
        <ConfirmDialog
          title={`Cancel ${c.title}?`}
          body={c.repeats ? 'Invitees are told and it comes off their calendars. Cancel just this one, or this and the later ones?' : 'Invitees are told and it comes off their calendars.'}
          confirmLabel={c.repeats ? 'Cancel this and later ones' : 'Cancel meeting'}
          pending={cancel.isPending}
          onClose={() => setConfirmCancel(false)}
          onConfirm={() => cancel.mutate(c.repeats)}
        />
      )}
      {confirmEnd && (
        <ConfirmDialog
          title="End the call for everyone?"
          body="Everyone in it is disconnected, and the chat shows the call ended."
          confirmLabel="End for everyone"
          pending={end.isPending}
          onClose={() => setConfirmEnd(false)}
          onConfirm={() => end.mutate()}
        />
      )}
    </div>
  )
}


/** Before a meeting opens (or one with a pasted link): when, how long, who, and Join once it's time. */
function MeetingDetails(props: { call: Call; open: boolean; onJoin: () => void; joining: boolean }) {
  const { call: c, open } = props
  const tz = useTimezone()
  const who = c.invite?.everyone
    ? 'Everyone in the room'
    : [...(c.invite?.tags ?? []).map((t) => `everyone tagged ${t.name}`), ...(c.invite?.users ?? []).map((u) => u.name)].join(', ')
  return (
    <div className="call-ready">
      <h2>{c.title}</h2>
      <dl className="meeting-facts">
        <dt>When</dt>
        <dd>
          {c.starts_at && dayAndTime(c.starts_at, tz)} · {c.duration_minutes} min{c.repeats ? ' · repeats' : ''}
        </dd>
        <dt>Who</dt>
        <dd>{who}</dd>
        <dt>Where</dt>
        <dd>{c.external_url ? 'A Google Meet or Zoom link' : 'A call in The Floor'}</dd>
        {c.description && (
          <>
            <dt>Notes</dt>
            <dd>{c.description}</dd>
          </>
        )}
      </dl>
      {open ? (
        <button className="btn primary" type="button" disabled={props.joining} onClick={props.onJoin}>
          <Icon name="video" />
          {props.joining ? 'Joining…' : c.external_url ? 'Open the meeting link' : 'Join meeting'}
        </button>
      ) : (
        <p className="muted">You can join from {timeOfDay(c.joinable_from, tz)}, 10 minutes before it starts.</p>
      )}
    </div>
  )
}

/** Over: how long it ran and who joined, or that it was cancelled or missed. */
function Finished({ call: c, home }: { call: Call; home: string }) {
  const tz = useTimezone()
  const heading = c.status === 'cancelled' ? 'This meeting was cancelled' : c.missed ? 'Nobody joined this meeting' : 'This call has ended'
  return (
    <div className="empty">
      <h2>{heading}</h2>
      {c.status === 'ended' && !c.missed && (
        <p>
          {c.started_at && dayAndTime(c.started_at, tz)} · {c.duration_minutes ?? 0} min
          {c.attended.length ? ` · ${c.attended.map((p) => p.name).join(', ')}` : ''}
        </p>
      )}
      {(c.status === 'cancelled' || c.missed) && <p>Schedule another from the room's Calls page whenever you need to.</p>}
      <Link className="btn" to={home}>
        Back
      </Link>
    </div>
  )
}

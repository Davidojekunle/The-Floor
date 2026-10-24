import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LiveKitRoom, VideoConference } from '@livekit/components-react'
import '@livekit/components-styles'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { callErrorText, endCall, getCall, joinCall, type JoinPass } from '../api/calls'
import { Avatar } from '../components/Avatar'
import { ConfirmDialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { Switch } from '../components/Switch'
import { useToast } from '../components/toastContext'
import { useRoom } from '../room/roomContext'

type Phase = 'ready' | 'joining' | 'in' | 'left' | 'error'

/** A call: LiveKit's ready-made conference screen, with who's in and "End for everyone" above it. */
export function CallPage() {
  const { callId = '' } = useParams()
  const { room } = useRoom()
  const toast = useToast()
  const queryClient = useQueryClient()
  const [phase, setPhase] = useState<Phase>('ready')
  const [pass, setPass] = useState<JoinPass>()
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
      setPass(await joinCall(room.id, callId))
      setPhase('in')
    } catch (e) {
      setPhase('error')
      setError(callErrorText(e instanceof ApiError ? e.code : undefined, "Couldn't join the call. Check your connection and try again."))
    }
  }

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
  const connected = live && phase === 'in' && pass

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
            {live ? (c.participants.length ? `${c.participants.length} in the call` : 'Nobody in yet') : 'Ended'}
          </span>
        </div>
        <span className="avstack" aria-label={c.participants.map((p) => p.name).join(', ')}>
          {c.participants.slice(0, 4).map((p) => (
            <Avatar key={p.id} name={p.name} size="sm" />
          ))}
        </span>
        {c.can_end && live && (
          <button className="btn danger-outline sm" type="button" onClick={() => setConfirmEnd(true)}>
            End for everyone
          </button>
        )}
      </header>

      {!live ? (
        <div className="empty">
          <h2>This call has ended</h2>
          <p>Start a new one from the room or the task whenever you need to.</p>
          <Link className="btn" to={home}>Back</Link>
        </div>
      ) : connected ? (
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

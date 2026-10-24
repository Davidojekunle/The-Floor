import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import DailyIframe, { type DailyCall } from '@daily-co/daily-js'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { callErrorText, endCall, getCall, joinCall } from '../api/calls'
import { Avatar } from '../components/Avatar'
import { ConfirmDialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { useToast } from '../components/toastContext'
import { useRoom } from '../room/roomContext'

type Phase = 'joining' | 'in' | 'left' | 'error'

/** Daily's call screen in the app's colours (its own layout, our palette). */
function theme() {
  const css = getComputedStyle(document.documentElement)
  const v = (name: string, fallback: string) => {
    const value = css.getPropertyValue(name).trim()
    return /^#[0-9a-f]{6}$/i.test(value) ? value : fallback // Daily wants plain hex
  }
  return {
    colors: {
      accent: v('--accent', '#2448c8'),
      accentText: '#ffffff',
      background: v('--surface', '#ffffff'),
      backgroundAccent: v('--bg', '#f6f6f5'),
      baseText: v('--text', '#141414'),
      border: v('--border', '#e4e4e1'),
      mainAreaBg: '#121212',
      mainAreaBgAccent: '#1e1e1e',
      mainAreaText: '#ffffff',
      supportiveText: v('--text-3', '#6b6b66'),
    },
  }
}

/** A call: Daily's ready-made screen, with who's in and "End for everyone" above it. */
export function CallPage() {
  const { callId = '' } = useParams()
  const { room } = useRoom()
  const toast = useToast()
  const queryClient = useQueryClient()
  const box = useRef<HTMLDivElement>(null)
  const frame = useRef<DailyCall | null>(null)
  const [phase, setPhase] = useState<Phase>('joining')
  const [error, setError] = useState<string>()
  const [attempt, setAttempt] = useState(0)
  const [confirmEnd, setConfirmEnd] = useState(false)

  const call = useQuery({ queryKey: ['call', room.id, callId], queryFn: () => getCall(room.id, callId), retry: false })
  const live = call.data?.status === 'live'

  // Join once the call is known to be live; leave and tidy up on the way out.
  useEffect(() => {
    if (!live || phase !== 'joining' || !box.current) return
    let cancelled = false
    const container = box.current
    ;(async () => {
      try {
        await DailyIframe.getCallInstance()?.destroy() // a stale one (a quick remount) would block a new frame
        const pass = await joinCall(room.id, callId)
        if (cancelled) return
        const options = { showLeaveButton: true, showFullscreenButton: true, iframeStyle: { width: '100%', height: '100%', border: '0' } }
        let f: DailyCall
        try {
          f = DailyIframe.createFrame(container, { ...options, theme: theme() })
        } catch {
          f = DailyIframe.createFrame(container, options) // a colour Daily won't take shouldn't stop the call
        }
        frame.current = f
        let failed = false
        // Daily couldn't connect (its account, the network): say so, rather than "You left the call"
        f.on('error', (ev) => {
          failed = true
          setPhase('error')
          setError(
            ev?.errorMsg === 'account-missing-payment-method'
              ? "Calls aren't set up yet on The Floor's video account. Tell the room's head."
              : 'The call dropped. Check your connection and try again.',
          )
        })
        f.on('left-meeting', () => {
          if (!failed) setPhase('left')
          void f.destroy()
          frame.current = null
          void queryClient.invalidateQueries({ queryKey: ['call', room.id, callId] })
        })
        await f.join({ url: pass.room_url, token: pass.token })
        if (!cancelled) setPhase('in')
      } catch (e) {
        if (cancelled) return
        setPhase('error')
        // Daily's own error event may already have said what went wrong; keep that
        setError((said) => said ?? callErrorText(e instanceof ApiError ? e.code : undefined, "Couldn't join the call. Check your connection and try again."))
      }
    })()
    return () => {
      cancelled = true
      void frame.current?.destroy()
      frame.current = null
    }
  }, [live, phase, attempt, room.id, callId, queryClient])

  // Ended for everyone (by someone else, or the server): close our screen too.
  useEffect(() => {
    if (call.data && call.data.status !== 'live' && frame.current) void frame.current.leave()
  }, [call.data])

  const end = useMutation({
    mutationFn: () => endCall(room.id, callId),
    onSuccess: () => {
      setConfirmEnd(false)
      toast('Call ended for everyone.')
      void queryClient.invalidateQueries({ queryKey: ['call', room.id, callId] })
    },
    onError: (e) => toast(callErrorText(e instanceof ApiError ? e.code : undefined, "Couldn't end the call. Try again.")),
  })

  const back = (
    <Link className="btn ghost sm" to={call.data?.task ? `/rooms/${room.id}/tasks/${call.data.task.id}` : `/rooms/${room.id}`}>
      <Icon name="back" size={14} />
      {call.data?.task ? call.data.task.title : room.name}
    </Link>
  )

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
  const rejoin = () => {
    setError(undefined)
    setPhase('joining')
    setAttempt((n) => n + 1)
  }

  return (
    <div className="call-page">
      <header className="call-bar">
        {back}
        <div className="call-title">
          <strong>{c.title}</strong>
          <span className="faint small">
            {c.status === 'live'
              ? c.participants.length
                ? `${c.participants.length} in the call`
                : 'Nobody in yet'
              : 'Ended'}
          </span>
        </div>
        <span className="avstack" aria-label={c.participants.map((p) => p.name).join(', ')}>
          {c.participants.slice(0, 4).map((p) => (
            <Avatar key={p.id} name={p.name} size="sm" />
          ))}
        </span>
        {c.can_end && c.status === 'live' && (
          <button className="btn danger-outline sm" type="button" onClick={() => setConfirmEnd(true)}>
            End for everyone
          </button>
        )}
      </header>

      {c.status !== 'live' ? (
        <div className="empty">
          <h2>This call has ended</h2>
          <p>Start a new one from the room or the task whenever you need to.</p>
          <Link className="btn" to={c.task ? `/rooms/${room.id}/tasks/${c.task.id}` : `/rooms/${room.id}`}>Back</Link>
        </div>
      ) : phase === 'left' ? (
        <div className="empty">
          <h2>You left the call</h2>
          <p>It carries on for everyone else, and ends 2 minutes after the last person leaves.</p>
          <div className="row-actions">
            <button className="btn primary" type="button" onClick={rejoin}>Rejoin</button>
            <Link className="btn" to={c.task ? `/rooms/${room.id}/tasks/${c.task.id}` : `/rooms/${room.id}`}>Back</Link>
          </div>
        </div>
      ) : phase === 'error' ? (
        <div className="empty" role="alert">
          <h2>Couldn't join</h2>
          <p>{error}</p>
          <button className="btn primary" type="button" onClick={rejoin}>Try again</button>
        </div>
      ) : null}

      {/* Daily's screen mounts here; it asks for the camera and microphone itself */}
      <div className="call-frame" ref={box} hidden={c.status !== 'live' || phase === 'left' || phase === 'error'}>
        {phase === 'joining' && <p className="call-note">Connecting…</p>}
      </div>

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

import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  blockUser, deleteDm, getDmThread, listDmMessages, markDmRead, sendDm, unblockUser, type DmMessage,
} from '../api/dms'
import { useAuth } from '../auth/useAuth'
import { ConfirmDialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { Menu } from '../components/Menu'
import { useToast } from '../components/toastContext'
import { useLive, useLiveSignals } from '../live/liveContext'
import { formatDay, timeOfDay } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'

/** One private conversation. Live: new messages arrive without refreshing (dm_created events). */
export function DmThreadPage() {
  const { threadId = '' } = useParams()
  const { user, refreshUser } = useAuth()
  const tz = useTimezone()
  const toast = useToast()
  const queryClient = useQueryClient()
  const { live } = useLive()
  const thread = useQuery({ queryKey: ['dm', threadId], queryFn: () => getDmThread(threadId), enabled: !!user?.direct_messages })
  const messages = useQuery({
    queryKey: ['dm-messages', threadId],
    queryFn: () => listDmMessages(threadId),
    enabled: !!user?.direct_messages,
    refetchInterval: live ? false : 10_000, // without the live socket, check every 10s
  })
  const [older, setOlder] = useState<DmMessage[]>([])
  const [hasOlder, setHasOlder] = useState<boolean | null>(null)
  const [text, setText] = useState('')
  const [confirm, setConfirm] = useState<null | 'block' | { del: DmMessage }>(null)
  const log = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

  // live: refetch on events for this conversation
  useLiveSignals((e) => {
    if (e.type === 'ready') {
      void messages.refetch()
      void thread.refetch()
      return
    }
    if (!('thread_id' in e) || e.thread_id !== threadId) return
    if (e.type === 'dm_created' || e.type === 'dm_deleted') void messages.refetch()
    if (e.type === 'dm_changed') void thread.refetch()
  })

  // reading it marks it read (and the badges update)
  const newest = messages.data?.items.at(-1)?.id
  useEffect(() => {
    if (!newest) return
    void markDmRead(threadId)
      .then(() => {
        void queryClient.invalidateQueries({ queryKey: ['dms'] })
        void refreshUser().catch(() => {})
      })
      .catch(() => {})
  }, [newest, threadId, queryClient, refreshUser])

  useLayoutEffect(() => {
    if (stick.current && log.current) log.current.scrollTop = log.current.scrollHeight
  }, [messages.data])

  const send = useMutation({
    mutationFn: (body: string) => sendDm(threadId, body),
    onSuccess: () => {
      setText('')
      stick.current = true
      void messages.refetch()
      void queryClient.invalidateQueries({ queryKey: ['dms'] })
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : "Couldn't send. Try again."),
  })
  const del = useMutation({
    mutationFn: (m: DmMessage) => deleteDm(threadId, m.id),
    onSuccess: () => {
      setConfirm(null)
      void messages.refetch()
    },
    onError: () => {
      setConfirm(null)
      toast("Couldn't delete it. Try again.")
    },
  })
  const blocking = useMutation({
    mutationFn: (block: boolean) => (block ? blockUser : unblockUser)(thread.data!.other.id),
    onSuccess: (_, block) => {
      setConfirm(null)
      void thread.refetch()
      void queryClient.invalidateQueries({ queryKey: ['dms'] })
      toast(block ? `You blocked ${thread.data!.other.name}.` : `You unblocked ${thread.data!.other.name}.`)
    },
    onError: () => {
      setConfirm(null)
      toast("Couldn't change that. Try again.")
    },
  })

  async function loadOlder() {
    const first = (older[0] ?? messages.data?.items[0])?.created_at
    if (!first) return
    stick.current = false
    const page = await listDmMessages(threadId, first)
    setOlder((o) => [...page.items, ...o])
    setHasOlder(page.has_more)
  }

  function submit(e?: FormEvent) {
    e?.preventDefault()
    const body = text.trim()
    if (body && !send.isPending) send.mutate(body)
  }

  if (user && !user.direct_messages) return <Navigate to="/rooms" replace />
  if (thread.isError || messages.isError) {
    const gone = thread.error instanceof ApiError && thread.error.status === 404
    return (
      <div className="container">
        <div className="page">
          <Link className="back" to="/messages">
            <Icon name="back" />
            Messages
          </Link>
          <div className="empty">
            <p>{gone ? 'This conversation was not found.' : "It didn't load. Refresh to try again."}</p>
          </div>
        </div>
      </div>
    )
  }
  const t = thread.data
  const items = [...older, ...(messages.data?.items ?? [])]
  const moreAbove = hasOlder ?? messages.data?.has_more ?? false
  let lastDay = ''

  return (
    <div className="container">
      <div className="page dm-page">
        <div>
          <Link className="back" to="/messages">
            <Icon name="back" />
            Messages
          </Link>
        </div>
        <div className="page-head">
          <div>
            <h1>{t?.other.name ?? '…'}</h1>
            <p className="sub">Only the two of you can see this conversation.</p>
          </div>
          {t && (
            <Menu
              label={`Options for ${t.other.name}`}
              items={[
                t.you_blocked
                  ? { label: `Unblock ${t.other.name}`, onSelect: () => blocking.mutate(false) }
                  : { label: `Block ${t.other.name}`, danger: true, onSelect: () => setConfirm('block') },
              ]}
            />
          )}
        </div>

        <div className="card dm-screen">
          <div className="dm-log" ref={log} onScroll={(e) => {
            const el = e.currentTarget
            stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
          }}>
            {moreAbove && (
              <div className="dm-older">
                <button type="button" className="btn ghost sm" onClick={() => void loadOlder()}>
                  Show older messages
                </button>
              </div>
            )}
            {messages.isPending && <p className="faint small dm-empty">Loading…</p>}
            {!messages.isPending && items.length === 0 && (
              <p className="faint small dm-empty">Say hello. Messages here are private to the two of you.</p>
            )}
            {items.map((m) => {
              const day = formatDay(m.created_at, tz)
              const showDay = day !== lastDay
              lastDay = day
              const mine = m.sender_id === user?.id
              return (
                <div key={m.id}>
                  {showDay && <div className="dm-day faint small">{day}</div>}
                  <div className={`dm-msg ${mine ? 'me' : 'them'}${m.deleted ? ' deleted' : ''}`}>
                    <div className="dm-bubble">
                      {m.deleted ? 'Message deleted' : m.body}
                      <span className="dm-time">{timeOfDay(m.created_at, tz)}</span>
                    </div>
                    {mine && !m.deleted && (
                      <button type="button" className="link-btn quiet small dm-del" onClick={() => setConfirm({ del: m })}>
                        Delete
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
          {t && !t.can_send ? (
            <p className="faint small dm-closed">
              {t.you_blocked
                ? `You blocked ${t.other.name}. Unblock them from the menu above to message again.`
                : "You can't send messages in this conversation."}
            </p>
          ) : (
            <form className="dm-compose" onSubmit={submit}>
              <label className="sr-only" htmlFor="dm-text">
                Message {t?.other.name}
              </label>
              <textarea
                id="dm-text"
                rows={2}
                maxLength={4000}
                value={text}
                placeholder={t ? `Message ${t.other.name}` : 'Message'}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault()
                    submit()
                  }
                }}
              />
              <button type="submit" className="btn primary" disabled={!text.trim() || send.isPending}>
                {send.isPending ? 'Sending…' : 'Send'}
              </button>
            </form>
          )}
        </div>
      </div>

      {confirm === 'block' && t && (
        <ConfirmDialog
          title={`Block ${t.other.name}?`}
          body="Neither of you can send messages in this conversation until you unblock them. They aren't told, and what's already been said stays."
          confirmLabel="Block"
          pending={blocking.isPending}
          onConfirm={() => blocking.mutate(true)}
          onClose={() => setConfirm(null)}
        />
      )}
      {confirm && typeof confirm === 'object' && (
        <ConfirmDialog
          title="Delete this message?"
          body="It's removed for both of you. This can't be undone."
          confirmLabel="Delete"
          pending={del.isPending}
          onConfirm={() => del.mutate(confirm.del)}
          onClose={() => setConfirm(null)}
        />
      )}
    </div>
  )
}

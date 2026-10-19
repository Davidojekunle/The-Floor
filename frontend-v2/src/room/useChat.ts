import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import { deleteMessage, listMessages, sendMessage, type Message, type MessagePage, type Ref, type ReplyQuote } from '../api/chat'
import type { UserBrief } from '../api/rooms'
import { useAuth } from '../auth/useAuth'
import { useLive, useLiveSignals } from '../live/liveContext'
import { useActionError } from './useRoomError'

const POLL_MS = 4000 // new messages while the chat is open and visible, only while the live socket is down
const REFRESH_MS = 60000 // re-read the latest page so deletions show up

/** A message being sent from this browser. Shown greyed until the server confirms it. */
export type LocalMessage = Message & {
  local: true
  failed: boolean
  draft: { body: string; task: Ref | null; stage: Ref | null; mentions?: UserBrief[]; replyTo?: ReplyQuote | null }
}
export type ChatItem = Message | LocalMessage
export const isLocal = (m: ChatItem): m is LocalMessage => 'local' in m

const byTime = (a: Message, b: Message) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id)

/**
 * Room chat. With the live socket up (phase 7), `message_created` and each reconnect trigger a catch-up fetch;
 * without it, the same catch-up runs every 4s (phase 6 polling). Messages are kept oldest → newest for rendering.
 * The catch-up uses `after=<newest id we have>` and repeats while `has_more`, which never skips a message.
 */
export function useChat(roomId: string) {
  const { user } = useAuth()
  const { live } = useLive()
  const onError = useActionError(roomId)
  const [messages, setMessages] = useState<Message[]>([])
  const [pending, setPending] = useState<LocalMessage[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [hasOlder, setHasOlder] = useState(false)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [lastReadAtOpen, setLastReadAtOpen] = useState<string | null>(null)
  const newest = useRef<string | null>(null) // newest message id we got from the server (never our optimistic ones)
  const busy = useRef(false)
  const again = useRef(false) // a new message was announced while a catch-up was running
  const localSeq = useRef(0)

  const merge = useCallback((incoming: Message[]) => {
    if (!incoming.length) return
    setMessages((prev) => {
      const map = new Map(prev.map((m) => [m.id, m]))
      for (const m of incoming) map.set(m.id, m)
      return [...map.values()].sort(byTime)
    })
  }, [])

  const applyFirstPage = useCallback((page: MessagePage) => {
    setMessages([...page.items].reverse())
    newest.current = page.items[0]?.id ?? null
    setHasOlder(page.has_more)
    setLastReadAtOpen(page.last_read_message_id)
    setStatus('ready')
  }, [])

  const load = useCallback(
    () =>
      listMessages(roomId).then(applyFirstPage, (err) => {
        onError(err)
        setStatus('error')
      }),
    [roomId, applyFirstPage, onError],
  )

  const poll = useCallback(async () => {
    if (document.visibilityState !== 'visible') return // catches up when the tab is shown again
    if (busy.current) {
      again.current = true
      return
    }
    busy.current = true
    try {
      do {
        again.current = false
        if (!newest.current) {
          const page = await listMessages(roomId)
          merge(page.items)
          newest.current = page.items[0]?.id ?? null
        } else {
          // Catch up without gaps: keep asking for what comes right after the newest we have.
          for (let i = 0; i < 20; i++) {
            const page = await listMessages(roomId, { after: newest.current })
            merge(page.items)
            if (page.items.length) newest.current = page.items[0].id
            if (!page.has_more) break
          }
        }
      } while (again.current)
    } catch (err) {
      // A 404 means we lost access: the shared handler shows the no-access screen. Anything else: try next tick.
      if (err instanceof ApiError && err.code === 'NOT_FOUND') onError(err)
    } finally {
      busy.current = false
    }
  }, [roomId, merge, onError])

  const refreshLatest = useCallback(async () => {
    if (document.visibilityState !== 'visible') return
    try {
      merge((await listMessages(roomId)).items)
    } catch {
      /* next time */
    }
  }, [roomId, merge])

  useEffect(() => {
    // One instance per room (ChatPage keys it by room id). Ignore a late first page if the chat already closed.
    let open = true
    listMessages(roomId).then(
      (page) => open && applyFirstPage(page),
      (err) => {
        if (!open) return
        onError(err)
        setStatus('error')
      },
    )
    const r = window.setInterval(() => void refreshLatest(), REFRESH_MS)
    const onVisible = () => document.visibilityState === 'visible' && void poll()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      open = false
      window.clearInterval(r)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [roomId, applyFirstPage, onError, poll, refreshLatest])

  // Fallback polling while the socket is down.
  useEffect(() => {
    if (live) return
    const p = window.setInterval(() => void poll(), POLL_MS)
    return () => window.clearInterval(p)
  }, [live, poll])

  useLiveSignals((signal) => {
    if (!('room_id' in signal)) return void poll() // 'ready': just (re)connected, fetch what we missed
    if (signal.room_id !== roomId) return
    if (signal.type === 'message_created') void poll()
    if (signal.type === 'message_deleted' && signal.message_id) {
      const id = signal.message_id
      setMessages((all) =>
        all.map((x) => (x.id === id ? { ...x, deleted: true, body: null, task: null, stage: null, event: null, can_delete: false } : x)),
      )
    }
  })

  const loadOlder = useCallback(async () => {
    const oldest = messages[0]?.id
    if (!oldest || loadingOlder || !hasOlder) return
    setLoadingOlder(true)
    try {
      const page = await listMessages(roomId, { before: oldest })
      merge(page.items)
      setHasOlder(page.has_more)
    } catch (err) {
      onError(err)
    } finally {
      setLoadingOlder(false)
    }
  }, [messages, loadingOlder, hasOlder, roomId, merge, onError])

  const deliver = useCallback(
    async (local: LocalMessage) => {
      try {
        const saved = await sendMessage(roomId, {
          body: local.draft.body,
          task_id: local.draft.task?.id,
          stage_id: local.draft.stage?.id,
          mention_ids: local.draft.mentions?.map((u) => u.id),
          reply_to_id: local.draft.replyTo?.id,
        })
        // Don't move `newest` forward: messages sent by others just before ours still need polling in.
        merge([saved])
        setPending((all) => all.filter((m) => m.id !== local.id))
        return { ok: true as const }
      } catch (err) {
        const linkGone = err instanceof ApiError && !!(err.fields?.task_id || err.fields?.stage_id)
        const replyGone = err instanceof ApiError && !!err.fields?.reply_to_id
        if (linkGone || replyGone) {
          setPending((all) => all.filter((m) => m.id !== local.id))
          return {
            ok: false as const,
            linkGone: true,
            message: replyGone
              ? 'The message you replied to was deleted. Your message is back in the box.'
              : "That task can't be linked any more. Your message is back in the box.",
          }
        }
        setPending((all) => all.map((m) => (m.id === local.id ? { ...m, failed: true } : m)))
        return { ok: false as const, linkGone: false, message: onError(err) }
      }
    },
    [roomId, merge, onError],
  )

  const send = useCallback(
    (draft: LocalMessage['draft']) => {
      const local: LocalMessage = {
        id: `local-${++localSeq.current}`,
        type: 'user',
        sender: user ? { id: user.id, name: user.name } : null,
        body: draft.body,
        task: draft.task,
        stage: draft.stage,
        mentions: draft.mentions ?? [],
        reply_to: draft.replyTo ?? null,
        event: null,
        created_at: new Date().toISOString(),
        deleted: false,
        can_delete: false,
        local: true,
        failed: false,
        draft,
      }
      setPending((all) => [...all, local])
      return deliver(local)
    },
    [user, deliver],
  )

  const retry = useCallback(
    (local: LocalMessage) => {
      setPending((all) => all.map((m) => (m.id === local.id ? { ...m, failed: false } : m)))
      return deliver({ ...local, failed: false })
    },
    [deliver],
  )

  const discard = useCallback((local: LocalMessage) => setPending((all) => all.filter((m) => m.id !== local.id)), [])

  const remove = useCallback(
    async (m: Message) => {
      await deleteMessage(roomId, m.id)
      setMessages((all) =>
        all.map((x) => (x.id === m.id ? { ...x, deleted: true, body: null, task: null, stage: null, event: null, can_delete: false } : x)),
      )
    },
    [roomId],
  )

  return {
    items: [...messages, ...pending] as ChatItem[],
    status,
    hasOlder,
    loadingOlder,
    loadOlder,
    lastReadAtOpen,
    newestServerId: messages.at(-1)?.id ?? null,
    send,
    retry,
    discard,
    remove,
    reload: load,
  }
}

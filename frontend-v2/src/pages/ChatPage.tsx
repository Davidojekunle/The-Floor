import { Fragment, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { markMessagesRead, type Message, type Ref, type ReplyQuote } from '../api/chat'
import type { UserBrief } from '../api/rooms'
import { listMembers } from '../api/members'
import { getTask, listTasks } from '../api/tasks'
import { useAuth } from '../auth/useAuth'
import { Avatar } from '../components/Avatar'
import { ConfirmDialog, Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { Menu } from '../components/Menu'
import { SwipeToReply } from '../components/SwipeToReply'
import { useToast } from '../components/toastContext'
import { dayKey, formatDay } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'
import { useRoom } from '../room/roomContext'
import { isLocal, useChat, type ChatItem, type LocalMessage } from '../room/useChat'
import { typingLabel, useTyping } from '../room/useTyping'

const MAX = 4000
const GROUP_MS = 5 * 60 * 1000 // consecutive messages from one person within 5 minutes share a header

/** Room chat, laid out like Slack's main pane: fills the space under the bar; only the message list scrolls. */
export function ChatPage() {
  const { room } = useRoom()
  return <ChatView key={room.id} /> // a fresh chat (messages, scroll, draft) per room
}

function ChatView() {
  const { room } = useRoom()
  const { user, refreshUser } = useAuth()
  const tz = useTimezone()
  const toast = useToast()
  const chat = useChat(room.id)

  const screen = useRef<HTMLElement>(null)
  const log = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const atBottom = useRef(true)
  const keepOffset = useRef<number | null>(null) // scrollHeight before older messages were added
  const seenCount = useRef(0)
  const lastMarked = useRef<string | null>(null)
  const shiftHeld = useRef(false) // Shift + Enter keeps a new line on keyboards that skip keydown (see onBeforeInput)
  // @mentions: who was picked from the list for this draft, and the "@que" being typed right now
  const [picked, setPicked] = useState<Map<string, string>>(() => new Map()) // user id -> name
  const [query, setQuery] = useState<{ text: string; start: number } | null>(null)
  const [active, setActive] = useState(0)
  const [replyTo, setReplyTo] = useState<Message | null>(null)
  const jumpTarget = useRef<string | null>(null) // a quoted message we're scrolling back to

  const [draft, setDraft] = useState('')
  const [link, setLink] = useState<{ task: Ref; stage: Ref | null } | null>(null)
  const [linking, setLinking] = useState(false)
  const [deleting, setDeleting] = useState<Message | null>(null)
  const [newBelow, setNewBelow] = useState(0)

  const members = useQuery({ queryKey: ['members', room.id], queryFn: () => listMembers(room.id) })
  const typing = useTyping(room.id, user?.id)

  // The shell's pane gives chat its full height (see .pane-scroll.fill in shell.css).

  // Keep the view pinned to the bottom when new messages arrive, unless the reader has scrolled up.
  useLayoutEffect(() => {
    const el = log.current
    if (!el) return
    if (keepOffset.current !== null) {
      el.scrollTop += el.scrollHeight - keepOffset.current // older messages were added above: stay put
      keepOffset.current = null
    } else if (atBottom.current) {
      el.scrollTop = el.scrollHeight
    } else {
      const fresh = chat.items.slice(seenCount.current).filter((m) => !isLocal(m) && m.sender?.id !== user?.id).length
      if (fresh) setNewBelow((n) => n + fresh)
    }
    const mineJustSent = chat.items.length > seenCount.current && isLocal(chat.items[chat.items.length - 1])
    if (mineJustSent) el.scrollTop = el.scrollHeight
    seenCount.current = chat.items.length
  }, [chat.items, user?.id])

  // A jump to a quoted message that wasn't loaded yet: look again each time older messages arrive.
  useEffect(() => {
    if (jumpTarget.current && !chat.loadingOlder) findJumpTarget()
  })

  // Mark read up to the newest message the reader has actually seen at the bottom, then refresh the badges.
  const markSeen = () => {
    const id = chat.newestServerId
    if (!id || id === lastMarked.current || !atBottom.current || document.visibilityState !== 'visible') return
    lastMarked.current = id
    void markMessagesRead(room.id, id).then(() => refreshUser(), () => {})
  }
  useEffect(markSeen)

  const onScroll = () => {
    const el = log.current!
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    if (atBottom.current && newBelow) setNewBelow(0)
    if (atBottom.current) markSeen()
    if (el.scrollTop < 120 && chat.hasOlder && !chat.loadingOlder) {
      keepOffset.current = el.scrollHeight
      void chat.loadOlder()
    }
  }

  const jumpDown = () => {
    const el = log.current!
    el.scrollTop = el.scrollHeight
    atBottom.current = true
    setNewBelow(0)
  }

  async function submit() {
    // Read the box itself: a phone keyboard can commit the last word in the same tick as Send, before state catches up.
    const body = (input.current?.value ?? draft).trim()
    if (!body) return
    // A pick counts only while its @Name is still in the text (deleting it un-mentions them).
    const mentions = [...picked].filter(([, name]) => body.includes(`@${name}`)).map(([id, name]) => ({ id, name }))
    const sent = { body, task: link?.task ?? null, stage: link?.stage ?? null, mentions, replyTo: replyTo ? quoteOf(replyTo) : null }
    setDraft('')
    setLink(null)
    setReplyTo(null)
    setPicked(new Map())
    setQuery(null)
    typing.stopped()
    atBottom.current = true
    resize(input.current, '')
    const result = await chat.send(sent)
    if (!result.ok && result.linkGone) {
      setDraft(body)
      toast(result.message)
    }
  }

  function startReply(m: Message) {
    setReplyTo(m)
    input.current?.focus()
  }

  /** Scroll to a quoted message, loading older pages until it's there, then flash it. */
  function jumpTo(id: string) {
    jumpTarget.current = id
    findJumpTarget()
  }

  function findJumpTarget() {
    const id = jumpTarget.current
    const el = id ? log.current?.querySelector<HTMLElement>(`[data-mid="${id}"]`) : null
    if (el) {
      jumpTarget.current = null
      el.scrollIntoView({ block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
      el.classList.remove('flash')
      void el.offsetWidth // restart the highlight if it's already running
      el.classList.add('flash')
      return
    }
    if (!id) return
    if (chat.hasOlder) {
      if (!chat.loadingOlder) {
        keepOffset.current = log.current?.scrollHeight ?? null
        void chat.loadOlder()
      }
    } else {
      jumpTarget.current = null
      toast("That message isn't in this chat any more.")
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    shiftHeld.current = e.shiftKey
    if (candidates.length > 0) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const step = e.key === 'ArrowDown' ? 1 : -1
        setActive((i) => (i + step + candidates.length) % candidates.length)
        return
      }
      if ((e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) || e.key === 'Tab') {
        e.preventDefault()
        choose(candidates[active] ?? candidates[0])
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setQuery(null)
        return
      }
    }
    if (e.key === 'Escape' && replyTo) {
      e.preventDefault()
      setReplyTo(null)
      return
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void submit()
    }
  }

  // Phone keyboards (Android especially) often send Enter mid-word with no usable keydown, so the browser
  // would insert a line break. Catch the line break itself: the keyboard's Send key sends. A native listener,
  // because React's onBeforeInput is a polyfill that never reports inputType.
  const submitRef = useRef(submit)
  const pickRef = useRef<(() => boolean) | null>(null) // picks the highlighted @name; false when the list is closed
  useEffect(() => {
    submitRef.current = submit
    pickRef.current = () => {
      if (!candidates.length) return false
      choose(candidates[active] ?? candidates[0])
      return true
    }
  })
  useEffect(() => {
    const el = input.current
    if (!el) return
    const onBeforeInput = (e: InputEvent) => {
      if ((e.inputType === 'insertLineBreak' || e.inputType === 'insertParagraph') && !shiftHeld.current) {
        e.preventDefault()
        if (!pickRef.current?.()) void submitRef.current()
      }
    }
    el.addEventListener('beforeinput', onBeforeInput)
    return () => el.removeEventListener('beforeinput', onBeforeInput)
  }, [])

  const people = members.data?.items ?? []
  const q = query?.text.toLowerCase() ?? ''
  const candidates: UserBrief[] = query
    ? people
        .map((m) => m.user)
        .filter((u) => u.id !== user?.id && u.name.toLowerCase().split(/\s+/).some((w) => w.startsWith(q)))
        .slice(0, 6)
    : []

  /** Swap the "@que" being typed for "@Full Name " and remember who it is. */
  function choose(person: UserBrief) {
    const el = input.current
    if (!el || !query) return
    const caret = el.selectionStart ?? el.value.length
    const before = el.value.slice(0, query.start)
    const text = `${before}@${person.name} ${el.value.slice(caret)}`
    const at = before.length + person.name.length + 2
    setDraft(text)
    setPicked((m) => new Map(m).set(person.id, person.name))
    setQuery(null)
    resize(el, text)
    typing.typed(text)
    requestAnimationFrame(() => el.setSelectionRange(at, at))
  }

  const typingNames = typing.typers.map((id) => people.find((m) => m.user.id === id)?.user.name).filter((n): n is string => !!n)

  return (
    <section className="chat-screen" ref={screen} aria-label={`${room.name} chat`}>
      <header className="chan-head">
        <div style={{ minWidth: 0 }}>
          <div className="name">
            <span className="hash">#</span>
            {room.name}
          </div>
          <div className="sub">Room chat · finished stages, blocks and approvals post here automatically</div>
        </div>
        <Link className="chan-people" to={`/rooms/${room.id}/members`} title="See members">
          <span className="avstack">
            {people.slice(0, 3).map((m) => (
              <Avatar key={m.membership_id} name={m.user.name} size="sm" />
            ))}
          </span>
          {room.member_count}
        </Link>
      </header>

      <div className="chat-body">
        <div className="chat-log" ref={log} onScroll={onScroll} aria-live="polite" aria-label="Messages">
          {chat.status === 'loading' && <p className="chat-note">Loading messages…</p>}
          {chat.status === 'error' && (
            <div className="chat-empty">
              <h2>Messages didn't load</h2>
              <button className="btn sm" type="button" onClick={() => void chat.reload()}>
                Try again
              </button>
            </div>
          )}
          {chat.status === 'ready' && chat.hasOlder && <p className="chat-note">{chat.loadingOlder ? 'Loading earlier messages…' : ' '}</p>}
          {chat.status === 'ready' && !chat.hasOlder && chat.items.length > 0 && (
            <p className="chat-note">This is the start of #{room.name}.</p>
          )}
          {chat.status === 'ready' && chat.items.length === 0 && (
            <div className="chat-empty">
              <h2>This is the start of #{room.name}</h2>
              <p>Say hello, or share how a task is going. Activity in the room appears here automatically.</p>
            </div>
          )}
          <MessageList
            items={chat.items}
            tz={tz}
            myId={user?.id}
            lastReadAtOpen={chat.lastReadAtOpen}
            onDelete={setDeleting}
            onRetry={(m) => void chat.retry(m)}
            onDiscard={chat.discard}
            onReply={startReply}
            onJump={jumpTo}
          />
        </div>
        {newBelow > 0 && (
          <button className="btn sm jump" type="button" onClick={jumpDown}>
            ↓ {newBelow} new message{newBelow > 1 ? 's' : ''}
          </button>
        )}
      </div>

      <div className="composer">
        <div className="composer-box">
          {replyTo && (
            <div className="reply-bar">
              <Icon name="reply" size={14} />
              <span className="reply-bar-text">
                Replying to <strong>{replyTo.sender?.name ?? 'an update'}</strong>
                <span className="reply-bar-quote">{oneLine(replyTo.body ?? '')}</span>
              </span>
              <button className="icon-btn" type="button" onPointerDown={(e) => e.preventDefault()} onClick={() => setReplyTo(null)} aria-label="Cancel reply">
                <Icon name="x" />
              </button>
            </div>
          )}
          {link && (
            <span className="ref-chip">
              ↳ {link.task.title}
              {link.stage ? ` · ${link.stage.title}` : ''}
              <button className="icon-btn" type="button" onClick={() => setLink(null)} aria-label="Remove linked task">
                <Icon name="x" />
              </button>
            </span>
          )}
          {candidates.length > 0 && (
            <div className="mention-list" id="mention-list" role="listbox" aria-label="Mention someone">
              {candidates.map((u, i) => (
                <button
                  key={u.id}
                  type="button"
                  role="option"
                  aria-selected={i === active}
                  className="mention-opt"
                  onPointerDown={(e) => e.preventDefault()} // keep the keyboard up
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(u)}
                >
                  <Avatar name={u.name} size="sm" />
                  {u.name}
                </button>
              ))}
            </div>
          )}
          <label htmlFor="chat-input" hidden>
            Message
          </label>
          <textarea
            id="chat-input"
            ref={input}
            rows={1}
            maxLength={MAX}
            placeholder={`Message #${room.name}`}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value)
              resize(e.target, e.target.value)
              typing.typed(e.target.value)
              setQuery(mentionQuery(e.target.value, e.target.selectionStart ?? e.target.value.length))
              setActive(0)
            }}
            onClick={(e) => setQuery(mentionQuery(e.currentTarget.value, e.currentTarget.selectionStart ?? 0))}
            onBlur={() => setQuery(null)}
            aria-autocomplete="list"
            aria-expanded={candidates.length > 0}
            aria-controls={candidates.length > 0 ? 'mention-list' : undefined}
            onKeyDown={onKey}
            onKeyUp={(e) => (shiftHeld.current = e.shiftKey)}
            enterKeyHint="send"
          />
          <div className="composer-tools">
            <button className="icon-btn" type="button" onClick={() => setLinking(true)} aria-label="Link a task" title="Link a task">
              <Icon name="link" />
            </button>
            <button
              className="send-btn"
              type="button"
              // Keep focus in the box: blurring it closes the keyboard and moves the layout before the tap
              // lands, which made the first tap on a phone miss. The keyboard stays up for the next message.
              onPointerDown={(e) => e.preventDefault()}
              onClick={() => void submit()}
              disabled={!draft.trim()}
              aria-label="Send"
              title="Send"
            >
              <Icon name="send" />
            </button>
          </div>
        </div>
        <div className="composer-hint">
          {/* Always rendered, so someone starting to type never moves the composer. */}
          <span className="typing" aria-live="polite">
            {typingNames.length > 0 && (
              <>
                {typingLabel(typingNames)}
                <span className="typing-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
              </>
            )}
          </span>
          {draft.length > 3500 ? (
            <span className="count-hint">{`${draft.length} / ${MAX}`}</span>
          ) : (
            <span className="hide-sm">
              <strong>Enter</strong> to send · <strong>Shift + Enter</strong> for a new line
            </span>
          )}
        </div>
      </div>

      {linking && (
        <LinkTaskDialog
          onClose={() => setLinking(false)}
          onPick={(l) => {
            setLink(l)
            setLinking(false)
            input.current?.focus()
          }}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title="Delete this message?"
          body='Everyone will see "This message was deleted." in its place.'
          confirmLabel="Delete"
          onConfirm={() =>
            void chat.remove(deleting).then(
              () => {
                setDeleting(null)
                toast('Message deleted.')
              },
              () => {
                setDeleting(null)
                toast("The message couldn't be deleted. Try again.")
              },
            )
          }
          onClose={() => setDeleting(null)}
        />
      )}
    </section>
  )
}

function resize(el: HTMLTextAreaElement | null, value: string) {
  if (!el) return
  el.style.height = 'auto'
  if (value) el.style.height = `${Math.min(el.scrollHeight + 2, 240)}px`
}

function MessageList(props: {
  items: ChatItem[]
  tz: string
  myId?: string
  lastReadAtOpen: string | null
  onDelete: (m: Message) => void
  onRetry: (m: LocalMessage) => void
  onDiscard: (m: LocalMessage) => void
  onReply: (m: Message) => void
  onJump: (id: string) => void
}) {
  const { items, tz, myId, lastReadAtOpen, onReply } = props
  const [today] = useState(() => dayKey(new Date().toISOString(), tz))
  const time = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: tz })
  const dayLabel = (key: string, iso: string) => {
    if (key === today) return 'Today'
    const y = new Date(`${today}T12:00:00Z`)
    y.setUTCDate(y.getUTCDate() - 1)
    return key === y.toISOString().slice(0, 10) ? 'Yesterday' : formatDay(iso, tz)
  }

  // The "New" line goes after the last message read when the chat was opened, if someone else wrote after it.
  const readIdx = lastReadAtOpen ? items.findIndex((m) => m.id === lastReadAtOpen) : -1
  const showNewAfter = readIdx >= 0 && items.slice(readIdx + 1).some((m) => !isLocal(m) && m.sender?.id !== myId) ? readIdx : -1

  const out: ReactNode[] = []
  let lastDay = ''
  let prev: ChatItem | null = null
  items.forEach((m, i) => {
    const day = dayKey(m.created_at, tz)
    if (day !== lastDay) {
      out.push(
        <div key={`d-${day}`} className="day-wrap">
          <div className="day-line" />
          <div className="day-sep">
            <span>{dayLabel(day, m.created_at)}</span>
          </div>
        </div>,
      )
      lastDay = day
      prev = null
    }
    if (m.type === 'system') {
      out.push(
        <SwipeToReply key={m.id} id={m.id} enabled={!m.deleted} onReply={() => onReply(m)}>
          <SystemLine m={m} at={time.format(new Date(m.created_at))} onReply={() => onReply(m)} />
        </SwipeToReply>,
      )
      prev = null
    } else {
      const cont =
        !!prev &&
        prev.type === 'user' &&
        !prev.deleted &&
        prev.sender?.id === m.sender?.id &&
        new Date(m.created_at).getTime() - new Date(prev.created_at).getTime() < GROUP_MS
      const canReply = !isLocal(m) && !m.deleted
      out.push(
        <SwipeToReply key={m.id} id={m.id} enabled={canReply} onReply={() => onReply(m)}>
          <UserMessage m={m} cont={cont && !m.reply_to} at={time.format(new Date(m.created_at))} {...props} />
        </SwipeToReply>,
      )
      prev = m
    }
    if (i === showNewAfter)
      out.push(
        <div key="new" className="new-sep" role="separator">
          <span>New</span>
        </div>,
      )
  })
  return <>{out}</>
}

function SystemLine({ m, at, onReply }: { m: Message; at: string; onReply: () => void }) {
  const { room } = useRoom()
  const body = m.body ?? ''
  // Turn the task's title inside the text into a link, when it's there.
  const i = m.task ? body.indexOf(m.task.title) : -1
  return (
    <div className="sys">
      <div className="sys-ico">
        <span>
          <Icon name="bolt" size={12} bold />
        </span>
      </div>
      <div>
        {i >= 0 && m.task ? (
          <>
            {body.slice(0, i)}
            <Link className="sys-link" to={`/rooms/${room.id}/tasks/${m.task.id}`}>
              {m.task.title}
            </Link>
            {body.slice(i + m.task.title.length)}
          </>
        ) : (
          body
        )}
        {m.event?.type === 'stage_done' && typeof m.event.detail?.result_url === 'string' && (
          <>
            {' · '}
            <a className="sys-link" href={m.event.detail.result_url} target="_blank" rel="noopener noreferrer">
              See the result
            </a>
          </>
        )}
      </div>
      <time>{at}</time>
      {!m.deleted && (
        <button className="icon-btn sys-reply" type="button" onClick={onReply} aria-label="Reply" title="Reply">
          <Icon name="reply" />
        </button>
      )}
    </div>
  )
}

function UserMessage(props: {
  m: ChatItem
  cont: boolean
  at: string
  myId?: string
  onDelete: (m: Message) => void
  onRetry: (m: LocalMessage) => void
  onDiscard: (m: LocalMessage) => void
  onReply: (m: Message) => void
  onJump: (id: string) => void
}) {
  const { m, cont, at, myId, onDelete, onRetry, onDiscard, onReply, onJump } = props
  const { room } = useRoom()
  const local = isLocal(m) ? m : null
  const name = m.sender?.name ?? 'Someone'
  const forMe = !m.deleted && !!myId && (m.mentions ?? []).some((u) => u.id === myId)
  const cls = ['msg', cont && 'cont', m.deleted && 'deleted', forMe && 'mentions-me', local && !local.failed && 'sending']
    .filter(Boolean)
    .join(' ')

  return (
    <div className={cls}>
      {cont ? <div className="stamp">{at}</div> : <Avatar name={name} />}
      <div style={{ minWidth: 0 }}>
        {!cont && (
          <div className="who">
            <strong>{name}</strong>
            <time>{at}</time>
          </div>
        )}
        {!m.deleted && m.reply_to && <Quote q={m.reply_to} onJump={onJump} />}
        <div className="text">
          {m.deleted ? 'This message was deleted.' : renderBody(m.body ?? '', m.mentions ?? [], myId)}
          {local && !local.failed && <span className="faint small"> Sending…</span>}
        </div>
        {!m.deleted && m.task && (
          <Link className="attach" to={`/rooms/${room.id}/tasks/${m.task.id}`}>
            <strong>{m.task.title}</strong>
            {m.stage && <span> · {m.stage.title} stage</span>}
          </Link>
        )}
        {local?.failed && (
          <div className="send-failed" role="alert">
            Not sent.{' '}
            <button className="link-btn" type="button" onClick={() => onRetry(local)}>
              Try again
            </button>{' '}
            ·{' '}
            <button className="link-btn" type="button" onClick={() => onDiscard(local)}>
              Discard
            </button>
          </div>
        )}
      </div>
      {!local && !m.deleted && (
        <div className="msg-tools">
          <button className="icon-btn reply-btn" type="button" onClick={() => onReply(m)} aria-label="Reply" title="Reply">
            <Icon name="reply" />
          </button>
          {m.can_delete && (
            <Menu label="Message actions" items={[{ label: 'Delete message', danger: true, onSelect: () => onDelete(m) }]} />
          )}
        </div>
      )}
    </div>
  )
}

function LinkTaskDialog({ onClose, onPick }: { onClose: () => void; onPick: (l: { task: Ref; stage: Ref | null }) => void }) {
  const { room } = useRoom()
  const navigate = useNavigate()
  const tasks = useQuery({ queryKey: ['tasks', room.id, 'all'], queryFn: () => listTasks(room.id) })
  const [taskId, setTaskId] = useState('')
  const [stageId, setStageId] = useState('')
  const chosen = taskId || tasks.data?.items[0]?.id || ''
  const detail = useQuery({ queryKey: ['task', room.id, chosen], queryFn: () => getTask(room.id, chosen), enabled: !!chosen })

  const items = tasks.data?.items ?? []
  return (
    <Dialog
      title="Link a task"
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn primary"
            type="button"
            disabled={!chosen}
            onClick={() => {
              const t = items.find((x) => x.id === chosen)!
              const s = detail.data?.stages.find((x) => x.id === stageId)
              onPick({ task: { id: t.id, title: t.title }, stage: s ? { id: s.id, title: s.title } : null })
            }}
          >
            Link
          </button>
        </>
      }
    >
      {tasks.isSuccess && items.length === 0 ? (
        <p className="muted">
          There are no tasks in this room yet.{' '}
          <button className="link-btn" type="button" onClick={() => navigate(`/rooms/${room.id}`)}>
            Go to Home
          </button>
        </p>
      ) : (
        <>
          <p className="muted small">The message will point to it, so people can open it in one click.</p>
          <div className="field">
            <label htmlFor="link-task">Task</label>
            <select
              className="select"
              id="link-task"
              value={chosen}
              onChange={(e) => {
                setTaskId(e.target.value)
                setStageId('')
              }}
            >
              {items.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="link-stage">
              Stage <span className="faint" style={{ fontWeight: 400 }}>(optional)</span>
            </label>
            <select className="select" id="link-stage" value={stageId} onChange={(e) => setStageId(e.target.value)}>
              <option value="">Whole task</option>
              {detail.data?.stages.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          </div>
        </>
      )}
    </Dialog>
  )
}

/** The quoted original above a reply. Tapping it scrolls back to it. */
function Quote({ q, onJump }: { q: ReplyQuote; onJump: (id: string) => void }) {
  return (
    <button className="quote-btn" type="button" onClick={() => onJump(q.id)} aria-label={`Go to the message from ${q.sender?.name ?? 'the room'}`}>
      <strong>{q.sender?.name ?? 'Update'}</strong>
      <span>{q.deleted ? 'Original message was deleted' : q.preview}</span>
    </button>
  )
}

const oneLine = (text: string) => {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > 140 ? `${flat.slice(0, 139).trimEnd()}…` : flat
}

/** How a reply being sent shows its original until the server's version arrives. */
function quoteOf(m: Message): ReplyQuote {
  return { id: m.id, type: m.type, sender: m.sender, preview: oneLine(m.body ?? ''), deleted: false }
}

/** The "@que" right before the caret, if the person is typing a mention. */
function mentionQuery(value: string, caret: number): { text: string; start: number } | null {
  const m = value.slice(0, caret).match(/(?:^|\s)@([^\s@]{0,30})$/)
  return m ? { text: m[1], start: caret - m[1].length - 1 } : null
}

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** A message's text with its @mentions marked (yours stronger) and links clickable. */
function renderBody(text: string, mentions: UserBrief[], myId?: string): ReactNode[] {
  const people = [...new Map(mentions.map((u) => [u.name, u])).values()].sort((a, b) => b.name.length - a.name.length)
  if (!people.length) return linkify(text)
  const re = new RegExp(`(${people.map((u) => `@${escapeRe(u.name)}`).join('|')})`, 'g')
  return text.split(re).map((part, i) => {
    if (i % 2 === 0) return <Fragment key={i}>{linkify(part)}</Fragment>
    const who = people.find((u) => `@${u.name}` === part)
    return (
      <span key={i} className={`mention${who?.id === myId ? ' me' : ''}`}>
        {part}
      </span>
    )
  })
}

/** Make http(s) links in a message clickable (shared progress updates carry one). Everything else stays plain text. */
function linkify(text: string): ReactNode[] {
  return text.split(/(https?:\/\/[^\s<>"]+[^\s<>".,;:!?)\]'])/g).map((part, i) =>
    i % 2 ? (
      <a key={i} href={part} target="_blank" rel="noopener noreferrer">
        {part}
      </a>
    ) : (
      part
    ),
  )
}

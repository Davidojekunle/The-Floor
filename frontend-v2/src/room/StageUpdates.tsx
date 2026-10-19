import { useState, type FormEvent } from 'react'
import { useInfiniteQuery, useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import type { Stage, TaskDetail } from '../api/tasks'
import { deleteUpdate, listStageUpdates, listTaskUpdates, postUpdate, type ProgressUpdate, type UpdatePage } from '../api/updates'
import { useAuth } from '../auth/useAuth'
import { ConfirmDialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { shortLink } from '../lib/embed'
import { Menu } from '../components/Menu'
import { useToast } from '../components/toastContext'
import { formatDay, relativeTime } from '../lib/dates'
import { plural } from '../lib/labels'
import { useTimezone } from '../lib/useTimezone'
import { useActionError } from './useRoomError'

/*
 * Progress updates (phase 6b): short notes on a stage, with an optional link.
 * Cache keys: ['updates', room, task, stageId] per stage and ['updates', room, task, 'all'] for the task feed.
 * Posting or deleting refetches both (prefix ['updates', room, task]) and adjusts the stage's update_count in place,
 * so the task itself isn't reloaded.
 */

const pageOpts = {
  initialPageParam: undefined as string | undefined,
  getNextPageParam: (last: UpdatePage) => (last.has_more ? last.items.at(-1)?.id : undefined),
}

function bumpCount(qc: QueryClient, roomId: string, taskId: string, stageId: string, by: number) {
  qc.setQueryData<TaskDetail>(['task', roomId, taskId], (t) =>
    t && { ...t, stages: t.stages.map((s) => (s.id === stageId ? { ...s, update_count: Math.max(0, s.update_count + by) } : s)) },
  )
  void qc.invalidateQueries({ queryKey: ['updates', roomId, taskId] })
}

/**
 * The updates row under a stage: "3 updates" (expands the list) and "Post an update" for participants.
 * `canPost` mirrors the server: approved task, and the stage involves me or I have stage.edit.
 */
export function StageUpdates({ task, stage, canPost }: { task: TaskDetail; stage: Stage; canPost: boolean }) {
  const [open, setOpen] = useState(false)
  const [composing, setComposing] = useState(false)
  const count = stage.update_count
  if (!count && !canPost) return null

  return (
    <div className="stage-updates">
      <div className="stage-updates-bar">
        {count > 0 && (
          <button type="button" className="link-btn quiet" aria-expanded={open} onClick={() => setOpen(!open)}>
            <Icon name={open ? 'down' : 'chev'} size={14} />
            {plural(count, 'update')}
          </button>
        )}
        {canPost && !composing && (
          <button type="button" className="link-btn" onClick={() => setComposing(true)}>
            <Icon name="plus" size={14} />
            Post an update
          </button>
        )}
      </div>
      {composing && (
        <UpdateComposer
          roomId={task.room_id}
          taskId={task.id}
          stage={stage}
          onClose={() => setComposing(false)}
          onPosted={() => {
            setComposing(false)
            setOpen(true)
          }}
        />
      )}
      {open && count > 0 && <StageUpdateList roomId={task.room_id} taskId={task.id} stageId={stage.id} />}
    </div>
  )
}

function StageUpdateList({ roomId, taskId, stageId }: { roomId: string; taskId: string; stageId: string }) {
  const q = useInfiniteQuery({
    queryKey: ['updates', roomId, taskId, stageId],
    queryFn: ({ pageParam }) => listStageUpdates(roomId, taskId, stageId, { before: pageParam }),
    ...pageOpts,
  })
  return <UpdateList q={q} roomId={roomId} taskId={taskId} showStage={false} />
}

/** Every stage's updates, newest first, at the bottom of the task page. Hidden until there's at least one. */
export function TaskUpdatesFeed({ task }: { task: TaskDetail }) {
  const total = task.stages.reduce((n, s) => n + s.update_count, 0)
  const q = useInfiniteQuery({
    queryKey: ['updates', task.room_id, task.id, 'all'],
    queryFn: ({ pageParam }) => listTaskUpdates(task.room_id, task.id, { before: pageParam }),
    enabled: total > 0,
    ...pageOpts,
  })
  if (!total) return null
  return (
    <section className="section">
      <h2>Updates</h2>
      <UpdateList q={q} roomId={task.room_id} taskId={task.id} showStage />
    </section>
  )
}

type UpdatesQuery = {
  data?: { pages: UpdatePage[] }
  isPending: boolean
  isError: boolean
  hasNextPage: boolean
  isFetchingNextPage: boolean
  fetchNextPage: () => unknown
  refetch: () => unknown
}

function UpdateList({ q, roomId, taskId, showStage }: { q: UpdatesQuery; roomId: string; taskId: string; showStage: boolean }) {
  if (q.isPending) return <p className="faint small">Loading updates…</p>
  if (q.isError)
    return (
      <p className="faint small">
        Updates didn't load.{' '}
        <button type="button" className="link-btn" onClick={() => void q.refetch()}>
          Try again
        </button>
      </p>
    )
  const items = q.data?.pages.flatMap((p) => p.items) ?? []
  if (!items.length) return <p className="faint small">No updates yet.</p>
  return (
    <>
      <ul className="updates">
        {items.map((u) => (
          <UpdateItem key={u.id} update={u} roomId={roomId} taskId={taskId} showStage={showStage} />
        ))}
      </ul>
      {q.hasNextPage && (
        <button type="button" className="btn sm ghost more-updates" disabled={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
          {q.isFetchingNextPage ? 'Loading…' : 'Show older updates'}
        </button>
      )}
    </>
  )
}

function UpdateItem({ update: u, roomId, taskId, showStage }: { update: ProgressUpdate; roomId: string; taskId: string; showStage: boolean }) {
  const { user } = useAuth()
  const tz = useTimezone()
  const qc = useQueryClient()
  const toast = useToast()
  const onError = useActionError(roomId)
  const [confirming, setConfirming] = useState(false)

  const remove = useMutation({
    mutationFn: () => deleteUpdate(roomId, taskId, u.stage.id, u.id),
    onSuccess: () => {
      setConfirming(false)
      bumpCount(qc, roomId, taskId, u.stage.id, -1)
      toast('Update deleted.')
    },
    onError: (err) => toast(onError(err)),
  })

  return (
    <li className="update">
      <div className="update-head">
        <strong>{u.author.id === user?.id ? 'You' : u.author.name}</strong>
        {showStage && <span className="update-stage">on {u.stage.title}</span>}
        <time className="faint" dateTime={u.created_at} title={formatDay(u.created_at, tz)}>
          {relativeTime(u.created_at, tz)}
        </time>
        {u.can_delete && (
          <span className="update-menu">
            <Menu label="Update actions" items={[{ label: 'Delete update', danger: true, onSelect: () => setConfirming(true) }]} />
          </span>
        )}
      </div>
      <p className="update-note">{u.note}</p>
      {u.link_url && (
        <a className="update-link" href={u.link_url} target="_blank" rel="noopener noreferrer">
          <Icon name="link" size={14} />
          <span>{shortLink(u.link_url)}</span>
        </a>
      )}
      {confirming && (
        <ConfirmDialog
          title="Delete this update?"
          body="It's removed from the stage for everyone. If it was also posted to chat, that message stays."
          confirmLabel="Delete update"
          pending={remove.isPending}
          onConfirm={() => remove.mutate()}
          onClose={() => setConfirming(false)}
        />
      )}
    </li>
  )
}

type ComposerProps = { roomId: string; taskId: string; stage: Stage; onClose: () => void; onPosted: () => void }

function UpdateComposer({ roomId, taskId, stage, onClose, onPosted }: ComposerProps) {
  const qc = useQueryClient()
  const toast = useToast()
  const onError = useActionError(roomId)
  const [note, setNote] = useState('')
  const [link, setLink] = useState('')
  const [withLink, setWithLink] = useState(false)
  const [share, setShare] = useState(false)
  const [errors, setErrors] = useState<{ note?: string; link?: string; form?: string }>({})
  const id = `upd-${stage.id}`

  const post = useMutation({
    mutationFn: () => postUpdate(roomId, taskId, stage.id, { note: note.trim(), link_url: link.trim() || null, share_to_chat: share }),
    onSuccess: () => {
      bumpCount(qc, roomId, taskId, stage.id, 1)
      toast(share ? 'Update posted, and shared in chat.' : 'Update posted.')
      onPosted()
    },
    onError: (err) => {
      if (err instanceof ApiError && err.fields)
        return setErrors({ note: err.fields.note, link: err.fields.link_url, form: err.fields.note || err.fields.link_url ? undefined : err.message })
      setErrors({ form: onError(err) })
    },
  })

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    const next = { note: note.trim() ? undefined : 'Write a short note first.', link: link.trim() ? linkProblem(link.trim()) : undefined }
    setErrors(next)
    if (!next.note && !next.link) post.mutate()
  }

  return (
    <form className="update-form" onSubmit={submit} aria-label={`Post an update on ${stage.title}`}>
      <div className="field">
        <label className="sr-only" htmlFor={`${id}-note`}>
          Update on {stage.title}
        </label>
        <textarea
          className="textarea"
          id={`${id}-note`}
          autoFocus
          maxLength={2000}
          rows={3}
          placeholder="What's the latest? e.g. Shot 3 of 5 scenes"
          value={note}
          aria-invalid={errors.note ? true : undefined}
          onChange={(e) => {
            setNote(e.target.value)
            setErrors((x) => ({ ...x, note: undefined, form: undefined }))
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit()
            if (e.key === 'Escape') onClose()
          }}
        />
        {errors.note && (
          <span className="err" role="alert">
            {errors.note}
          </span>
        )}
      </div>
      {withLink && (
        <div className="field">
          <label htmlFor={`${id}-link`}>Link</label>
          <input
            className="input"
            id={`${id}-link`}
            type="url"
            inputMode="url"
            maxLength={2000}
            placeholder="https://"
            value={link}
            aria-invalid={errors.link ? true : undefined}
            onChange={(e) => {
              setLink(e.target.value)
              setErrors((x) => ({ ...x, link: undefined, form: undefined }))
            }}
          />
          {errors.link ? (
            <span className="err" role="alert">
              {errors.link}
            </span>
          ) : (
            <span className="hint">A draft, a folder, a photo: anything people can open in a browser.</span>
          )}
        </div>
      )}
      {errors.form && (
        <span className="err small" role="alert">
          {errors.form}
        </span>
      )}
      <div className="update-form-foot">
        <div className="update-form-opts">
          {!withLink && (
            <button type="button" className="link-btn" onClick={() => setWithLink(true)}>
              <Icon name="link" size={14} />
              Add a link
            </button>
          )}
          <label className="check">
            <input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} />
            Also post to room chat
          </label>
        </div>
        <div className="update-form-acts">
          <button type="button" className="btn sm ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn sm primary" disabled={post.isPending}>
            Post update
          </button>
        </div>
      </div>
    </form>
  )
}

/** Same rule as the server: a web link with a host. */
function linkProblem(value: string): string | undefined {
  try {
    const u = new URL(value)
    if ((u.protocol === 'http:' || u.protocol === 'https:') && u.hostname) return undefined
  } catch {
    /* fall through */
  }
  return 'Use a web link starting with http:// or https://.'
}

/** "docs.google.com/document/d/1x…" */

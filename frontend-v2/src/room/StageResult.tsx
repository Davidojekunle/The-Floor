import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { setStageResult, type Stage, type TaskDetail } from '../api/tasks'
import { useAuth } from '../auth/useAuth'
import { ConfirmDialog, Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { useToast } from '../components/toastContext'
import { relativeTime } from '../lib/dates'
import { checkLink, embedFor, RESULT_HINT, shortLink } from '../lib/embed'
import { useTimezone } from '../lib/useTimezone'
import { useActionError } from './useRoomError'

/** The link fields, shared by "Mark done" and "Add the result". */
export function ResultFields(props: {
  url: string
  note: string
  error?: string
  onUrl: (v: string) => void
  onNote: (v: string) => void
  autoFocus?: boolean
}) {
  return (
    <>
      <div className="field">
        <label htmlFor="result-url">
          Link to the result <span className="faint" style={{ fontWeight: 400 }}>(optional)</span>
        </label>
        <input
          className="input"
          id="result-url"
          type="url"
          inputMode="url"
          autoFocus={props.autoFocus}
          placeholder="https://"
          value={props.url}
          maxLength={2000}
          aria-invalid={props.error ? true : undefined}
          aria-describedby="result-url-hint"
          onChange={(e) => props.onUrl(e.target.value)}
        />
        <span className={props.error ? 'err' : 'hint'} id="result-url-hint" role={props.error ? 'alert' : undefined}>
          {props.error ?? RESULT_HINT}
        </span>
      </div>
      {props.url.trim() && (
        <div className="field">
          <label htmlFor="result-note">
            Note <span className="faint" style={{ fontWeight: 400 }}>(optional)</span>
          </label>
          <input
            className="input"
            id="result-note"
            maxLength={300}
            placeholder="e.g. Final cut, 32 seconds"
            value={props.note}
            onChange={(e) => props.onNote(e.target.value)}
          />
        </div>
      )}
    </>
  )
}

/** "Mark done" with an optional link to the finished work. */
export function DoneDialog(props: { stage: Pick<Stage, 'title'>; pending: boolean; onClose: () => void; onDone: (url: string, note: string) => void }) {
  const [url, setUrl] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string>()
  const submit = () => {
    const e = checkLink(url)
    if (e) return setError(e)
    props.onDone(url.trim(), note.trim())
  }
  return (
    <Dialog
      title={`Mark ${props.stage.title} done?`}
      onClose={props.onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={props.onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" disabled={props.pending} onClick={submit}>
            <Icon name="check" />
            Mark done
          </button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
        style={{ display: 'grid', gap: 16 }}
      >
        <ResultFields
          url={url}
          note={note}
          error={error}
          autoFocus
          onUrl={(v) => {
            setUrl(v)
            setError(undefined)
          }}
          onNote={setNote}
        />
        <button type="submit" hidden />
      </form>
    </Dialog>
  )
}

/** On a done stage: the result in one line, with Add / Change for the people who can. */
export function StageResultLine({ task, stage: s }: { task: TaskDetail; stage: Stage }) {
  const [editing, setEditing] = useState(false)
  if (!s.result && !s.can_set_result) return null
  return (
    <div className="result-line">
      {s.result ? (
        <a href={s.result.url} target="_blank" rel="noopener noreferrer" className="update-link">
          <Icon name="link" size={14} />
          <span>{shortLink(s.result.url)}</span>
        </a>
      ) : (
        <span className="faint small">No result linked yet.</span>
      )}
      {s.can_set_result && (
        <button className="link-btn" type="button" onClick={() => setEditing(true)}>
          {s.result ? 'Change' : 'Add the result'}
        </button>
      )}
      {editing && <ResultDialog task={task} stage={s} onClose={() => setEditing(false)} />}
    </div>
  )
}

function ResultDialog({ task, stage: s, onClose }: { task: TaskDetail; stage: Stage; onClose: () => void }) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const onError = useActionError(task.room_id)
  const [url, setUrl] = useState(s.result?.url ?? '')
  const [note, setNote] = useState(s.result?.note ?? '')
  const [error, setError] = useState<string>()
  const [confirmRemove, setConfirmRemove] = useState(false)
  const save = useMutation({
    mutationFn: (v: { url: string | null; note: string | null }) => setStageResult(task.room_id, task.id, s.id, v.url, v.note),
    onSuccess: (updated, v) => {
      queryClient.setQueryData(['task', task.room_id, task.id], updated)
      toast(v.url ? `Result saved on ${s.title}.` : `Result removed from ${s.title}.`)
      onClose()
    },
    onError: (err) => {
      if (err instanceof ApiError && err.fields?.url) return setError('Paste a full web link, starting with https://')
      toast(onError(err))
    },
  })
  const submit = () => {
    if (!url.trim()) return setError('Paste the link to the finished work.')
    const e = checkLink(url)
    if (e) return setError(e)
    save.mutate({ url: url.trim(), note: note.trim() || null })
  }
  if (confirmRemove)
    return (
      <ConfirmDialog
        title={`Remove the result from ${s.title}?`}
        body="The link is taken off the task. The file itself isn't touched."
        confirmLabel="Remove"
        pending={save.isPending}
        onConfirm={() => save.mutate({ url: null, note: null })}
        onClose={() => setConfirmRemove(false)}
      />
    )
  return (
    <Dialog
      title={s.result ? `Change the result of ${s.title}` : `Add the result of ${s.title}`}
      onClose={onClose}
      actions={
        <>
          {s.result && (
            <button className="btn ghost danger-text" type="button" onClick={() => setConfirmRemove(true)} style={{ marginRight: 'auto' }}>
              Remove
            </button>
          )}
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" disabled={save.isPending} onClick={submit}>
            Save
          </button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
        style={{ display: 'grid', gap: 16 }}
      >
        <ResultFields
          url={url}
          note={note}
          error={error}
          autoFocus
          onUrl={(v) => {
            setUrl(v)
            setError(undefined)
          }}
          onNote={setNote}
        />
        <button type="submit" hidden />
      </form>
    </Dialog>
  )
}

/** "Work so far": each finished stage's result in order, playable in place. */
export function WorkSoFar({ task }: { task: TaskDetail }) {
  const done = task.stages.filter((s) => s.result)
  if (!done.length) return null
  return (
    <section className="section" aria-labelledby="work-so-far">
      <h2 id="work-so-far">Work so far</h2>
      <ol className="work-list">
        {done.map((s) => (
          <WorkItem key={s.id} stage={s} />
        ))}
      </ol>
    </section>
  )
}

function WorkItem({ stage: s }: { stage: Stage }) {
  const { user } = useAuth()
  const tz = useTimezone()
  const r = s.result!
  return (
    <li className="work-item">
      <div className="work-head">
        <strong>{s.title}</strong>
        <span className="faint small">
          {r.by ? (r.by.id === user?.id ? 'You' : r.by.name) : 'Someone'} · {relativeTime(r.at, tz)}
        </span>
      </div>
      {r.note && <p className="work-note">{r.note}</p>}
      <ResultPreview url={r.url} title={s.title} />
    </li>
  )
}

/** A player, picture or link card for one result. Frames load on tap. */
export function ResultPreview({ url, title }: { url: string; title: string }) {
  const e = embedFor(url)
  const [open, setOpen] = useState(false)
  const [broken, setBroken] = useState(false)
  const openLink = (
    <a className="update-link" href={url} target="_blank" rel="noopener noreferrer">
      <Icon name="link" size={14} />
      <span>Open in {e.provider}</span>
    </a>
  )

  if (e.kind === 'image' && !broken)
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" className="work-media">
        <img src={e.src} alt={`Result of ${title}`} loading="lazy" onError={() => setBroken(true)} />
      </a>
    )
  if (e.kind === 'video' && !broken)
    return (
      <div className="work-media">
        <video src={e.src} controls preload="metadata" playsInline onError={() => setBroken(true)} />
      </div>
    )
  if (e.kind !== 'frame') return <div className="work-card">{openLink}</div>

  return (
    <div className="work-embed">
      <div className={`work-frame ${e.shape}`}>
        {open ? (
          <iframe
            src={e.src}
            title={`${title}: ${e.provider}`}
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen; clipboard-write"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
          />
        ) : (
          <button type="button" className="work-poster" onClick={() => setOpen(true)} aria-label={`${e.verb} ${title} from ${e.provider}`}>
            {e.thumb && <img src={e.thumb} alt="" loading="lazy" />}
            <span className="work-play">
              {e.verb === 'Play' ? <PlayGlyph /> : <Icon name="layers" size={18} />}
              {e.verb} · {e.provider}
            </span>
          </button>
        )}
      </div>
      <div className="work-foot">
        {openLink}
        {open && e.provider === 'Google Drive' && (
          <span className="faint small">Asked to sign in or request access? The file isn't shared with you yet.</span>
        )}
      </div>
    </div>
  )
}

function PlayGlyph() {
  return (
    <svg className="i" width="16" height="16" viewBox="0 0 256 256" aria-hidden="true">
      <path fill="currentColor" d="M240,128a15.74,15.74,0,0,1-7.6,13.51L88.32,229.65a16,16,0,0,1-16.2.3A15.86,15.86,0,0,1,64,216.13V39.87a15.86,15.86,0,0,1,8.12-13.82,16,16,0,0,1,16.2.3L232.4,114.49A15.74,15.74,0,0,1,240,128Z" />
    </svg>
  )
}

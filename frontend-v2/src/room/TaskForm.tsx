import { useState, type FormEvent, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { listMembers, listTags } from '../api/members'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { Menu, type MenuItem } from '../components/Menu'
import { useTimezone } from '../lib/useTimezone'
import { useRoom } from './roomContext'
import { FieldErrors, newStage, type DraftStage, type DraftTask } from './taskDraft'
import { useRoomError } from './useRoomError'

const PLACEHOLDERS = ['e.g. Script', 'e.g. Shoot', 'e.g. Edit']

// Server messages we rewrite in plainer words. Unknown ones are shown as sent.
const FRIENDLY: Record<string, string> = {
  title: 'Give the task a name.',
}

type Props = {
  initial: DraftTask
  submitLabel: string
  pendingLabel: string
  cancelHref: string
  onSubmit: (draft: DraftTask) => Promise<void>
  /** Extra controls under the stages heading, e.g. "Use a template". Receives a setter for stages. */
  stagesAddon?: (setStages: (s: DraftStage[], title?: string) => void) => ReactNode
}

export function TaskForm({ initial, submitLabel, pendingLabel, cancelHref, onSubmit, stagesAddon }: Props) {
  const { room } = useRoom()
  const { user } = useAuth()
  const tz = useTimezone()
  const onRoomError = useRoomError()

  const [draft, setDraft] = useState<DraftTask>(initial)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const tags = useQuery({ queryKey: ['tags', room.id], queryFn: () => listTags(room.id) })
  const members = useQuery({ queryKey: ['members', room.id], queryFn: () => listMembers(room.id) })

  // Editing a field clears its error; the rest stay until the next submit.
  const clearErrors = (match: (key: string) => boolean) =>
    setErrors((e) => (Object.keys(e).some(match) ? Object.fromEntries(Object.entries(e).filter(([k]) => !match(k))) : e))
  const set = (patch: Partial<DraftTask>) => {
    if ('title' in patch) clearErrors((k) => k === 'title')
    if ('due' in patch) clearErrors((k) => k === 'due_date' || /^stages\.\d+\.due_date$/.test(k))
    setDraft((d) => ({ ...d, ...patch }))
  }
  const setStages = (fn: (s: DraftStage[]) => DraftStage[]) =>
    setDraft((d) => {
      const stages = fn(d.stages)
      if (stages[0]) stages[0] = { ...stages[0], parallel: false } // the first stage can't run in parallel
      return { ...d, stages }
    })
  const updateStage = (i: number, patch: Partial<DraftStage>) => {
    for (const field of ['title', 'due'] as const)
      if (field in patch) clearErrors((k) => k === `stages.${i}.${field === 'due' ? 'due_date' : field}`)
    setStages((all) => all.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  }
  const clearStageErrors = () => clearErrors((k) => k.startsWith('stages')) // indexes shift: they'd point at the wrong row
  const move = (i: number, by: number) => {
    clearStageErrors()
    setStages((all) => {
      const next = [...all]
      ;[next[i], next[i + by]] = [next[i + by], next[i]]
      return next
    })
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    const local: Record<string, string> = {}
    if (!draft.title.trim()) local.title = FRIENDLY.title
    if (!draft.due) local.due_date = 'Pick a due date.'
    draft.stages.forEach((s, i) => {
      if (!s.title.trim()) local[`stages.${i}.title`] = 'Name this stage.'
      if (s.due && draft.due && s.due > draft.due) local[`stages.${i}.due_date`] = "A stage can't be due after the task."
    })
    setErrors(local)
    if (Object.keys(local).length) return

    setPending(true)
    try {
      await onSubmit(draft)
    } catch (err) {
      const fields = err instanceof FieldErrors || err instanceof ApiError ? err.fields : undefined
      if (fields) {
        const mapped: Record<string, string> = {}
        for (const [key, msg] of Object.entries(fields)) mapped[key] = FRIENDLY[key] ?? msg
        setErrors(mapped)
      } else setFormError(onRoomError(err))
    } finally {
      setPending(false)
    }
  }

  const stageErr = (i: number, field: string) => errors[`stages.${i}.${field}`]
  const otherStageErrors = Object.entries(errors).filter(
    ([k]) => k.startsWith('stages') && !/^stages\.\d+\.(title|due_date)$/.test(k),
  )

  return (
    <form className="form-card" onSubmit={handleSubmit} noValidate>
      {formError && (
        <div className="form-error" role="alert">
          {formError}
        </div>
      )}

      <div className="field">
        <label htmlFor="t-title">Task name</label>
        <input
          className="input"
          id="t-title"
          maxLength={200}
          placeholder="e.g. Brand launch video"
          value={draft.title}
          onChange={(e) => set({ title: e.target.value })}
          aria-invalid={errors.title ? true : undefined}
          aria-describedby={errors.title ? 't-title-err' : undefined}
        />
        {errors.title && (
          <span className="err" id="t-title-err" role="alert">
            {errors.title}
          </span>
        )}
      </div>

      <div className="two">
        <div className="field">
          <label htmlFor="t-due">Due date</label>
          <input
            className="input"
            type="date"
            id="t-due"
            value={draft.due}
            onChange={(e) => set({ due: e.target.value })}
            aria-invalid={errors.due_date ? true : undefined}
          />
          {errors.due_date ? (
            <span className="err" role="alert">
              {errors.due_date}
            </span>
          ) : (
            <span className="hint">Due at the end of that day ({tz.replace(/_/g, ' ')} time).</span>
          )}
        </div>
        {draft.description === null && (
          <div className="field add-desc">
            <button className="link-btn" type="button" onClick={() => set({ description: '' })}>
              <Icon name="plus" /> Add a description
            </button>
          </div>
        )}
      </div>

      {draft.description !== null && (
        <div className="field">
          <label htmlFor="t-desc">Description</label>
          <textarea
            className="textarea"
            id="t-desc"
            maxLength={5000}
            placeholder="What's this task about?"
            value={draft.description}
            onChange={(e) => set({ description: e.target.value })}
          />
        </div>
      )}

      <div className="section" style={{ gap: 12 }}>
        <div className="section-h" style={{ alignItems: 'flex-start' }}>
          <div>
            <h2>Stages</h2>
            <p className="muted small" style={{ marginTop: 2 }}>
              Stages happen in order. Each one starts when the one before it is done.
            </p>
          </div>
          {stagesAddon?.((stages, title) =>
            setDraft((d) => ({ ...d, stages, title: d.title.trim() ? d.title : (title ?? d.title) })),
          )}
        </div>

        <div className="stage-rows">
          {draft.stages.map((s, i) => {
            const items: MenuItem[] = []
            if (i > 0)
              items.push({
                label: s.parallel ? 'Run after the previous stage' : 'Run at the same time as the previous stage',
                onSelect: () => updateStage(i, { parallel: !s.parallel }),
              })
            items.push({
              label: s.showDue ? 'Remove due date' : 'Add a due date',
              onSelect: () => updateStage(i, s.showDue ? { showDue: false, due: '' } : { showDue: true }),
            })
            if (i > 0) items.push({ label: 'Move up', onSelect: () => move(i, -1) })
            if (i < draft.stages.length - 1) items.push({ label: 'Move down', onSelect: () => move(i, 1) })
            if (draft.stages.length > 1)
              items.push('divider', {
                label: 'Remove stage',
                danger: true,
                onSelect: () => {
                  clearStageErrors()
                  setStages((all) => all.filter((_, j) => j !== i))
                },
              })

            return (
              <div className="srow" key={s.key}>
                <span className="n">{i + 1}</span>
                <input
                  className="input"
                  placeholder={PLACEHOLDERS[i] ?? 'Stage name'}
                  maxLength={120}
                  value={s.title}
                  onChange={(e) => updateStage(i, { title: e.target.value })}
                  aria-label={`Stage ${i + 1} name`}
                  aria-invalid={stageErr(i, 'title') ? true : undefined}
                />
                <select
                  className="select"
                  value={s.owner}
                  onChange={(e) => updateStage(i, { owner: e.target.value })}
                  aria-label={`Who does stage ${i + 1}`}
                >
                  {s.owner === 'keep' && <option value="keep">{s.keepLabel}</option>}
                  <option value="">Choose who does it</option>
                  {(tags.data?.items.length ?? 0) > 0 && (
                    <optgroup label="Everyone with a tag">
                      {tags.data?.items.map((t) => (
                        <option key={t.id} value={`tag:${t.id}`}>
                          {t.name} ({t.member_count})
                        </option>
                      ))}
                    </optgroup>
                  )}
                  <optgroup label="A person">
                    {members.data?.items.map((m) => (
                      <option key={m.user.id} value={`user:${m.user.id}`}>
                        {m.user.id === user?.id ? 'Me' : m.user.name}
                      </option>
                    ))}
                  </optgroup>
                </select>
                <Menu label={`Stage ${i + 1} options`} items={items} />
                {(s.parallel && i > 0) || s.showDue ? (
                  <div className="srow-extra">
                    {s.parallel && i > 0 && (
                      <span className="alongside">
                        <Icon name="parallel" size={14} /> Runs at the same time as stage {i}
                      </span>
                    )}
                    {s.showDue && (
                      <label className="stage-due">
                        <span>Stage due</span>
                        <input
                          className="input"
                          type="date"
                          value={s.due}
                          max={draft.due || undefined}
                          onChange={(e) => updateStage(i, { due: e.target.value })}
                          aria-invalid={stageErr(i, 'due_date') ? true : undefined}
                        />
                      </label>
                    )}
                  </div>
                ) : null}
                {(stageErr(i, 'title') || stageErr(i, 'due_date')) && (
                  <span className="err srow-err" role="alert">
                    {stageErr(i, 'title') ?? stageErr(i, 'due_date')}
                  </span>
                )}
              </div>
            )
          })}
        </div>

        {otherStageErrors.length > 0 && (
          <span className="err small" role="alert">
            {otherStageErrors[0][1]}
          </span>
        )}

        <div>
          <button
            className="btn ghost sm"
            type="button"
            onClick={() => setStages((all) => [...all, newStage()])}
            disabled={draft.stages.length >= 30}
          >
            <Icon name="plus" />
            Add stage
          </button>
        </div>
      </div>

      <div className="form-foot">
        <Link className="btn ghost" to={cancelHref}>
          Cancel
        </Link>
        <button className="btn primary" type="submit" disabled={pending}>
          {pending ? pendingLabel : submitLabel}
        </button>
      </div>
    </form>
  )
}

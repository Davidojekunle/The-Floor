import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { listTags } from '../api/members'
import { createTemplate, getTemplate, updateTemplate, type Template, type TemplateInput } from '../api/tasks'
import { Icon } from '../components/Icon'
import { Menu, type MenuItem } from '../components/Menu'
import { useToast } from '../components/toastContext'
import { useCan, useRoom } from '../room/roomContext'
import { useRoomError } from '../room/useRoomError'

type Row = { key: number; title: string; tagId: string; parallel: boolean }
let nextKey = 1
const row = (patch: Partial<Row> = {}): Row => ({ key: nextKey++, title: '', tagId: '', parallel: false, ...patch })

/** New template (no :templateId) or edit an existing one. */
export function TemplateEditorPage() {
  const { templateId } = useParams()
  const { room } = useRoom()
  const canManage = useCan('task.create')

  const existing = useQuery({
    queryKey: ['template', room.id, templateId],
    queryFn: () => getTemplate(room.id, templateId!),
    enabled: !!templateId,
  })

  if (!canManage) return <Navigate to={`/rooms/${room.id}`} replace />
  if (templateId && existing.isPending) return <div className="page" />
  if (templateId && existing.isError)
    return (
      <div className="page">
        <div className="empty">
          <h2>This template doesn't exist any more</h2>
          <Link className="btn" to={`/rooms/${room.id}/templates`}>
            Back to templates
          </Link>
        </div>
      </div>
    )

  return <Editor key={templateId ?? 'new'} template={existing.data} />
}

function Editor({ template }: { template?: Template }) {
  const { room } = useRoom()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const onError = useRoomError()
  const back = `/rooms/${room.id}/templates`

  const [name, setName] = useState(template?.name ?? '')
  const [rows, setRows] = useState<Row[]>(() =>
    template
      ? template.stages.map((s) => row({ title: s.title, tagId: s.tag?.id ?? '', parallel: s.parallel_with_previous }))
      : [row()],
  )
  const [errors, setErrors] = useState<Record<string, string>>({})

  const tags = useQuery({ queryKey: ['tags', room.id], queryFn: () => listTags(room.id) })

  const save = useMutation({
    mutationFn: (body: TemplateInput) => (template ? updateTemplate(room.id, template.id, body) : createTemplate(room.id, body)),
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ['templates', room.id] })
      queryClient.setQueryData(['template', room.id, saved.id], saved)
      toast(template ? 'Template saved.' : `Template "${saved.name}" created.`)
      navigate(back)
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) setErrors({ name: `There's already a template called "${name.trim()}".` })
      else if (err instanceof ApiError && err.fields) setErrors(err.fields)
      else setErrors({ form: onError(err) })
    },
  })

  const setAll = (fn: (r: Row[]) => Row[]) =>
    setRows((all) => {
      const next = fn(all)
      if (next[0]) next[0] = { ...next[0], parallel: false }
      return next
    })
  const update = (i: number, patch: Partial<Row>) => setAll((all) => all.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  function submit(e: FormEvent) {
    e.preventDefault()
    const local: Record<string, string> = {}
    if (!name.trim()) local.name = 'Give the template a name.'
    if (rows.some((r) => !r.title.trim())) local.stages = 'Every stage needs a name.'
    setErrors(local)
    if (Object.keys(local).length) return
    save.mutate({
      name: name.trim(),
      stages: rows.map((r, i) => ({ title: r.title.trim(), tag_id: r.tagId || null, parallel_with_previous: i > 0 && r.parallel })),
    })
  }

  const stageError = errors.stages ?? Object.entries(errors).find(([k]) => k.startsWith('stages.'))?.[1]

  return (
    <div className="page">
      <div>
        <Link className="back" to={back}>
          <Icon name="back" />
          Templates
        </Link>
      </div>
      <div className="page-head">
        <div>
          <h1>{template ? 'Edit template' : 'New template'}</h1>
          <p className="sub">
            {template ? "Tasks already made from it won't change." : 'Pick a tag for each stage so new tasks reach the right people.'}
          </p>
        </div>
      </div>

      <form className="form-card" onSubmit={submit} noValidate>
        {errors.form && (
          <div className="form-error" role="alert">
            {errors.form}
          </div>
        )}
        <div className="field">
          <label htmlFor="tpl-name">Template name</label>
          <input
            className="input"
            id="tpl-name"
            maxLength={100}
            placeholder="e.g. Video shoot"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={errors.name ? true : undefined}
            aria-describedby={errors.name ? 'tpl-name-err' : undefined}
          />
          {errors.name && (
            <span className="err" id="tpl-name-err" role="alert">
              {errors.name}
            </span>
          )}
        </div>

        <div className="section" style={{ gap: 12 }}>
          <h2>Stages</h2>
          <div className="stage-rows">
            {rows.map((r, i) => {
              const items: MenuItem[] = []
              if (i > 0)
                items.push({
                  label: r.parallel ? 'Run after the previous stage' : 'Run at the same time as the previous stage',
                  onSelect: () => update(i, { parallel: !r.parallel }),
                })
              if (i > 0)
                items.push({
                  label: 'Move up',
                  onSelect: () =>
                    setAll((all) => {
                      const next = [...all]
                      ;[next[i - 1], next[i]] = [next[i], next[i - 1]]
                      return next
                    }),
                })
              if (rows.length > 1)
                items.push('divider', { label: 'Remove stage', danger: true, onSelect: () => setAll((all) => all.filter((_, j) => j !== i)) })
              return (
                <div className="srow" key={r.key}>
                  <span className="n">{i + 1}</span>
                  <input
                    className="input"
                    placeholder="Stage name"
                    maxLength={120}
                    value={r.title}
                    onChange={(e) => update(i, { title: e.target.value })}
                    aria-label={`Stage ${i + 1} name`}
                  />
                  <select className="select" value={r.tagId} onChange={(e) => update(i, { tagId: e.target.value })} aria-label={`Tag for stage ${i + 1}`}>
                    <option value="">No tag</option>
                    {tags.data?.items.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                  {items.length > 0 ? <Menu label={`Stage ${i + 1} options`} items={items} /> : <span />}
                  {r.parallel && i > 0 && (
                    <div className="srow-extra">
                      <span className="alongside">
                        <Icon name="parallel" size={14} /> Runs at the same time as stage {i}
                      </span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          {stageError && (
            <span className="err small" role="alert">
              {stageError}
            </span>
          )}
          <div>
            <button className="btn ghost sm" type="button" onClick={() => setAll((all) => [...all, row()])} disabled={rows.length >= 30}>
              <Icon name="plus" />
              Add stage
            </button>
          </div>
        </div>

        <div className="form-foot">
          <Link className="btn ghost" to={back}>
            Cancel
          </Link>
          <button className="btn primary" type="submit" disabled={save.isPending}>
            {save.isPending ? 'Saving…' : template ? 'Save template' : 'Create template'}
          </button>
        </div>
      </form>
    </div>
  )
}

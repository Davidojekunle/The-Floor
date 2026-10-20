import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { errorMessage } from '../api/errorMessage'
import { listMembers, listTags } from '../api/members'
import { CreateTask, type CreateTaskInput } from '../api/tasks'
import { StageDraftCard } from '../components/StageDraftCard'
import {
  buildCreateInput,
  newStageDraft,
  type StageDraft,
  type TaskDraft,
} from '../lib/TasksForm'
import { useCan, useRoom } from '../room/useRoom'

const MAX_STAGES = 30

export function CreateTaskPage() {
  const { room, refreshRoom } = useRoom()
  const canCreate = useCan('task.create')
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [draft, setDraft] = useState<TaskDraft>(() => ({
    title: '',
    description: '',
    start: '',
    due: '',
    stages: [newStageDraft()],
  }))
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)

  const tags = useQuery({
    queryKey: ['tags', room.id],
    queryFn: () => listTags(room.id),
  })
  const members = useQuery({
    queryKey: ['members', room.id, 'all'],
    queryFn: () => listMembers(room.id, 1, 100),
  })

  const create = useMutation({
    mutationFn: (input: CreateTaskInput) => CreateTask(room.id, input),
    onSuccess: async (task) => {
      await queryClient.invalidateQueries({ queryKey: ['tasks', room.id] })
      navigate(`/room/${room.id}/tasks/${task.id}`)
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.status === 403) refreshRoom()
        if (err.fields) {
          setFieldErrors(err.fields)
          setFormError('Please fix the highlighted fields.')
          return
        }
      }
      setFormError(errorMessage(err))
    },
  })

  function updateStage(index: number, patch: Partial<StageDraft>) {
    setDraft((d) => ({
      ...d,
      stages: d.stages.map((s, i) => (i === index ? { ...s, ...patch } : s)),
    }))
  }

  // The first stage can never run "with the previous one".
  function clearFirstParallel(stages: StageDraft[]): StageDraft[] {
    const first = stages[0]
    if (!first) return stages
    const copy = [...stages]
    copy[0] = { ...first, parallel: false }
    return copy
  }

  function moveStage(index: number, direction: -1 | 1) {
    setDraft((d) => {
      const other = index + direction
      const a = d.stages[index]
      const b = d.stages[other]
      if (!a || !b) return d
      const stages = [...d.stages]
      stages[index] = b
      stages[other] = a
      return { ...d, stages: clearFirstParallel(stages) }
    })
  }

  function removeStage(index: number) {
    setDraft((d) => {
      if (d.stages.length <= 1) return d
      const stages = d.stages.filter((_, i) => i !== index)
      return { ...d, stages: clearFirstParallel(stages) }
    })
  }

  function addStage() {
    setDraft((d) => ({ ...d, stages: [...d.stages, newStageDraft()] }))
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setFieldErrors({})
    setFormError(null)
    create.mutate(buildCreateInput(draft))
  }

  if (!canCreate) return <p>You don't have permission to create tasks.</p>
  if (tags.isPending || members.isPending) return <p>Loading...</p>
  if (tags.isError || members.isError) {
    return <p>Could not load this room's tags and members.</p>
  }

  const fe = (name: string) => fieldErrors[name]

  return (
    <div>
      <p>
        <Link to={`/room/${room.id}`}>&larr; Back to tasks</Link>
      </p>
      <h1>New task</h1>

      <form onSubmit={handleSubmit}>
        {formError && <div className="form-error">{formError}</div>}

        <div className="field">
          <label htmlFor="task-title">Title</label>
          <input
            id="task-title"
            value={draft.title}
            onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
            maxLength={200}
            required
          />
          {fe('title') && <span className="field-error">{fe('title')}</span>}
        </div>

        <div className="field">
          <label htmlFor="task-description">Description (optional)</label>
          <textarea
            id="task-description"
            rows={3}
            value={draft.description}
            onChange={(e) =>
              setDraft((d) => ({ ...d, description: e.target.value }))
            }
            maxLength={5000}
          />
          {fe('description') && (
            <span className="field-error">{fe('description')}</span>
          )}
        </div>

        <div className="field">
          <label htmlFor="task-start">Start (optional)</label>
          <input
            id="task-start"
            type="datetime-local"
            value={draft.start}
            onChange={(e) => setDraft((d) => ({ ...d, start: e.target.value }))}
          />
          {fe('start_date') && (
            <span className="field-error">{fe('start_date')}</span>
          )}
        </div>

        <div className="field">
          <label htmlFor="task-due">Due</label>
          <input
            id="task-due"
            type="datetime-local"
            value={draft.due}
            onChange={(e) => setDraft((d) => ({ ...d, due: e.target.value }))}
            required
          />
          {fe('due_date') && <span className="field-error">{fe('due_date')}</span>}
        </div>

        <h2>Stages</h2>
        <p className="muted">
          Stages run one after another. Tick "runs at the same time" to run a
          stage together with the one before it.
        </p>
        {fe('stages') && <div className="form-error">{fe('stages')}</div>}

        {draft.stages.map((stage, i) => (
          <StageDraftCard
            key={stage.key}
            index={i}
            count={draft.stages.length}
            draft={stage}
            tags={tags.data.items}
            members={members.data.items}
            errors={fieldErrors}
            onChange={(patch) => updateStage(i, patch)}
            onMove={(direction) => moveStage(i, direction)}
            onRemove={() => removeStage(i)}
          />
        ))}

        <p>
          <button
            type="button"
            onClick={addStage}
            disabled={draft.stages.length >= MAX_STAGES}
          >
            + Add stage
          </button>
        </p>

        <button className="primary" type="submit" disabled={create.isPending}>
          {create.isPending ? 'Creating...' : 'Create task'}
        </button>
      </form>
    </div>
  )
}
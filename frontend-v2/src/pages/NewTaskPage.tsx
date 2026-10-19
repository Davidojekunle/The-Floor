import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { createTask, listTemplates } from '../api/tasks'
import { Icon } from '../components/Icon'
import { Menu, type MenuItem } from '../components/Menu'
import { useToast } from '../components/toastContext'
import { endOfDayIso } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'
import { useCan, useRoom } from '../room/roomContext'
import { TaskForm } from '../room/TaskForm'
import { blankDraft, newStage, ownerFields, type DraftTask } from '../room/taskDraft'

export function NewTaskPage() {
  const { room } = useRoom()
  const tz = useTimezone()
  const canCreate = useCan('task.create')
  const canPropose = useCan('task.propose')
  const proposing = !canCreate // same form; the server creates it as a pending proposal
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const [initial] = useState(() => blankDraft(tz))

  const templates = useQuery({ queryKey: ['templates', room.id], queryFn: () => listTemplates(room.id) })

  if (!canCreate && !canPropose) return <Navigate to={`/rooms/${room.id}`} replace />

  async function submit(d: DraftTask) {
    const task = await createTask(room.id, {
      title: d.title.trim(),
      description: d.description?.trim() || null,
      due_date: endOfDayIso(d.due, tz),
      stages: d.stages.map((s, i) => ({
        title: s.title.trim(),
        ...ownerFields(s.owner),
        due_date: s.due ? endOfDayIso(s.due, tz) : null,
        parallel_with_previous: i > 0 && s.parallel,
      })),
    })
    queryClient.setQueryData(['task', room.id, task.id], task)
    void queryClient.invalidateQueries({ queryKey: ['tasks', room.id] })
    void queryClient.invalidateQueries({ queryKey: ['me-tasks'] })
    if (task.approval_status === 'pending') {
      toast("Sent for approval. You'll see the decision under Your proposals.")
    } else {
      const ready = task.stages.filter((s) => s.status === 'todo').map((s) => s.title)
      toast(`Task created. ${ready.join(' and ')} can start now.`)
    }
    navigate(`/rooms/${room.id}/tasks/${task.id}`)
  }

  const templateItems = (fill: (s: DraftTask['stages'], title?: string) => void): MenuItem[] => [
    ...(templates.data?.items ?? []).map((t) => ({
      label: (
        <span className="ri">
          {t.name}
          <small>{t.stages.map((s) => s.title).join(' → ')}</small>
        </span>
      ),
      onSelect: () => {
        fill(
          t.stages.map((s) => newStage({ title: s.title, owner: s.tag ? `tag:${s.tag.id}` : '', parallel: s.parallel_with_previous })),
          t.name,
        )
        toast(`Filled in from "${t.name}". Change anything you need.`)
      },
    })),
    ...(canCreate
      ? (['divider', { label: 'Manage templates', onSelect: () => navigate(`/rooms/${room.id}/templates`) }] as MenuItem[])
      : []),
  ]

  return (
    <div className="page">
      <div>
        <Link className="back" to={`/rooms/${room.id}`}>
          <Icon name="back" />
          {room.name}
        </Link>
      </div>
      <div className="page-head">
        <div>
          <h1>{proposing ? 'Propose a task' : 'New task'}</h1>
          <p className="sub">
            {proposing
              ? `The head of ${room.name} reviews it first. Until then, only you and the heads can see it.`
              : `Everyone in ${room.name} will see it.`}
          </p>
        </div>
      </div>
      <TaskForm
        initial={initial}
        submitLabel={proposing ? 'Send for approval' : 'Create task'}
        pendingLabel={proposing ? 'Sending…' : 'Creating…'}
        cancelHref={`/rooms/${room.id}`}
        onSubmit={submit}
        stagesAddon={(fill) =>
          templates.data?.items.length ? (
            <Menu
              label="Use a template"
              triggerClassName="btn sm"
              trigger={
                <>
                  Use a template
                  <Icon name="down" />
                </>
              }
              items={templateItems(fill)}
            />
          ) : canCreate ? (
            <Link className="btn ghost sm" to={`/rooms/${room.id}/templates`}>
              Templates
            </Link>
          ) : null
        }
      />
    </div>
  )
}

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { deleteTemplate, listTemplates, type Template } from '../api/tasks'
import { ConfirmDialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { Menu } from '../components/Menu'
import { useToast } from '../components/toastContext'
import { useCan, useRoom } from '../room/roomContext'
import { useRoomError } from '../room/useRoomError'

/** Reusable stage lists, e.g. "Video shoot: Script → Shoot → Edit". */
export function TemplatesPage() {
  const { room } = useRoom()
  const canManage = useCan('task.create')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const onError = useRoomError()
  const [deleting, setDeleting] = useState<Template | null>(null)

  const templates = useQuery({ queryKey: ['templates', room.id], queryFn: () => listTemplates(room.id) })

  const remove = useMutation({
    mutationFn: (t: Template) => deleteTemplate(room.id, t.id),
    onSuccess: (_, t) => {
      void queryClient.invalidateQueries({ queryKey: ['templates', room.id] })
      setDeleting(null)
      toast(`Template "${t.name}" deleted.`)
    },
    onError: (err) => toast(onError(err)),
  })

  if (!canManage) return <Navigate to={`/rooms/${room.id}`} replace />

  const items = templates.data?.items ?? []
  const base = `/rooms/${room.id}/templates`

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
          <h1>Templates</h1>
          <p className="sub">Stage lists you can reuse when you create a task.</p>
        </div>
        <Link className="btn primary" to={`${base}/new`}>
          <Icon name="plus" />
          New template
        </Link>
      </div>

      <div className="list">
        {templates.isPending ? (
          <div className="empty">
            <p>Loading templates…</p>
          </div>
        ) : items.length === 0 ? (
          <div className="empty">
            <h2>No templates yet</h2>
            <p>Save the stages you use often, like Script → Shoot → Edit, and fill them into new tasks in one click.</p>
          </div>
        ) : (
          items.map((t) => (
            <div className="row" key={t.id}>
              <div className="main">
                <div className="title">{t.name}</div>
                <div className="meta">{t.stages.map((s) => s.title).join(' → ')}</div>
              </div>
              <Menu
                label={`Actions for ${t.name}`}
                items={[
                  { label: 'Edit', onSelect: () => navigate(`${base}/${t.id}`) },
                  'divider',
                  { label: 'Delete template', danger: true, onSelect: () => setDeleting(t) },
                ]}
              />
            </div>
          ))
        )}
      </div>
      <p className="faint small">Changing a template doesn't change tasks already made from it.</p>

      {deleting && (
        <ConfirmDialog
          title={`Delete "${deleting.name}"?`}
          body="Tasks made from it stay as they are."
          confirmLabel="Delete template"
          pending={remove.isPending}
          onConfirm={() => remove.mutate(deleting)}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  )
}

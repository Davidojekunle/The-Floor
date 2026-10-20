import type { Member, Tag } from '../api/members'
import type { StageDraft } from '../lib/TasksForm'

type Props = {
  index: number
  count: number
  draft: StageDraft
  tags: Tag[]
  members: Member[]
  errors: Record<string, string>
  onChange: (patch: Partial<StageDraft>) => void
  onMove: (direction: -1 | 1) => void
  onRemove: () => void
}

export function StageDraftCard({
  index,
  count,
  draft,
  tags,
  members,
  errors,
  onChange,
  onMove,
  onRemove,
}: Props) {
  const err = (field: string) => errors[`stages.${index}.${field}`]
  const id = (field: string) => `stage-${draft.key}-${field}`

  function toggleAssignee(userId: string) {
    onChange({
      assigneeIds: draft.assigneeIds.includes(userId)
        ? draft.assigneeIds.filter((x) => x !== userId)
        : [...draft.assigneeIds, userId],
    })
  }

  return (
    <div className="stage-draft">
      <div className="task-card-top">
        <strong>Stage {index + 1}</strong>
        <div className="actions">
          <button type="button" disabled={index === 0} onClick={() => onMove(-1)}>
            Up
          </button>
          <button
            type="button"
            disabled={index === count - 1}
            onClick={() => onMove(1)}
          >
            Down
          </button>
          <button type="button" disabled={count === 1} onClick={onRemove}>
            Remove
          </button>
        </div>
      </div>

      <div className="field">
        <label htmlFor={id('title')}>Title</label>
        <input
          id={id('title')}
          value={draft.title}
          onChange={(e) => onChange({ title: e.target.value })}
          maxLength={200}
          required
        />
        {err('title') && <span className="field-error">{err('title')}</span>}
      </div>

      <div className="field">
        <label htmlFor={id('tag')}>Role tag (optional)</label>
        <select
          id={id('tag')}
          value={draft.tagId}
          onChange={(e) => onChange({ tagId: e.target.value })}
        >
          <option value="">No tag</option>
          {tags.map((tag) => (
            <option key={tag.id} value={tag.id}>
              {tag.name}
            </option>
          ))}
        </select>
        {err('tag_id') && <span className="field-error">{err('tag_id')}</span>}
      </div>

      <div className="field">
        <span>People (optional)</span>
        <div className="checks">
          {members.map((m) => (
            <label key={m.membership_id}>
              <input
                type="checkbox"
                checked={draft.assigneeIds.includes(m.user.id)}
                onChange={() => toggleAssignee(m.user.id)}
              />
              {m.user.name}
            </label>
          ))}
        </div>
        {err('assignee_ids') && (
          <span className="field-error">{err('assignee_ids')}</span>
        )}
      </div>

      <div className="field">
        <label htmlFor={id('due')}>Stage due date (optional)</label>
        <input
          id={id('due')}
          type="datetime-local"
          value={draft.due}
          onChange={(e) => onChange({ due: e.target.value })}
        />
        {err('due_date') && (
          <span className="field-error">{err('due_date')}</span>
        )}
      </div>

      {index > 0 && (
        <div className="field">
          <div className="checks">
            <label>
              <input
                type="checkbox"
                checked={draft.parallel}
                onChange={(e) => onChange({ parallel: e.target.checked })}
              />
              Runs at the same time as the previous stage
            </label>
          </div>
          {err('parallel_with_previous') && (
            <span className="field-error">{err('parallel_with_previous')}</span>
          )}
        </div>
      )}
    </div>
  )
}
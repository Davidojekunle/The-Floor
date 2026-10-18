import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { errorMessage } from '../api/errorMessage'
import {
  listMembers,
  listTags,
  removeMember,
  setMemberTags,
  type Member,
} from '../api/members'
import { useCan, useRoom } from '../room/useRoom'

function roleLabel(role: string) {
  return role === 'temp_head' ? 'temp head' : role
}

export function MembersSection() {
  const { room, refreshRoom } = useRoom()
  const canTag = useCan('tag.manage')
  const canRemove = useCan('member.remove')
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [selected, setSelected] = useState<string[]>([])

  const members = useQuery({
    queryKey: ['members', room.id, page],
    queryFn: () => listMembers(room.id, page),
  })

  const tags = useQuery({
    queryKey: ['tags', room.id],
    queryFn: () => listTags(room.id),
    enabled: canTag,
  })
  const allTags = tags.data?.items ?? []

  function refreshLists() {
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: ['members', room.id] }),
      queryClient.invalidateQueries({ queryKey: ['tags', room.id] }),
    ])
  }

  function onError(err: unknown) {
    if (err instanceof ApiError && err.status === 403) refreshRoom()
  }

  const saveTags = useMutation({
    mutationFn: (vars: { membershipId: string; tagIds: string[] }) =>
      setMemberTags(room.id, vars.membershipId, vars.tagIds),
    onSuccess: async () => {
      setEditingId(null)
      await refreshLists()
    },
    onError,
  })

  const remove = useMutation({
    mutationFn: (membershipId: string) => removeMember(room.id, membershipId),
    onSuccess: async () => {
      await refreshLists()
      refreshRoom() // member_count changed
    },
    onError,
  })

  const actionError = saveTags.error ?? remove.error

  function startEdit(member: Member) {
    setEditingId(member.membership_id)
    setSelected(member.tags.map((t) => t.id))
  }

  function toggle(tagId: string) {
    setSelected((cur) =>
      cur.includes(tagId) ? cur.filter((id) => id !== tagId) : [...cur, tagId],
    )
  }

  function handleRemove(member: Member) {
    const ok = window.confirm(
      `Remove ${member.user.name} from ${room.name}? They will lose access immediately.`,
    )
    if (ok) remove.mutate(member.membership_id)
  }

  if (members.isPending) return <p>Loading members...</p>
  if (members.isError) return <p>Could not load members.</p>

  const { items, total, limit } = members.data
  const totalPages = Math.max(1, Math.ceil(total / limit))

  return (
    <section>
      <h2>Members ({total})</h2>

      {actionError != null && (
        <div className="form-error">{errorMessage(actionError)}</div>
      )}

      {items.map((m) => (
        <div className="row" key={m.membership_id}>
          <div>
            <strong>{m.user.name}</strong>{' '}
            <span className="badge">{roleLabel(m.role)}</span>
            <div>
              {m.tags.length === 0 ? (
                <span className="muted">No tags</span>
              ) : (
                m.tags.map((t) => (
                  <span className="chip" key={t.id}>
                    {t.name}
                  </span>
                ))
              )}
            </div>

            {editingId === m.membership_id && (
              <div className="tag-picker">
                {allTags.length === 0 ? (
                  <p>Create a tag first.</p>
                ) : (
                  allTags.map((tag) => (
                    <label key={tag.id}>
                      <input
                        type="checkbox"
                        checked={selected.includes(tag.id)}
                        onChange={() => toggle(tag.id)}
                      />{' '}
                      {tag.name}
                    </label>
                  ))
                )}
                <div className="actions">
                  <button
                    disabled={saveTags.isPending}
                    onClick={() =>
                      saveTags.mutate({
                        membershipId: m.membership_id,
                        tagIds: selected,
                      })
                    }
                  >
                    Save tags
                  </button>
                  <button onClick={() => setEditingId(null)}>Cancel</button>
                </div>
              </div>
            )}
          </div>

          <div className="actions">
            {canTag && editingId !== m.membership_id && (
              <button onClick={() => startEdit(m)}>Edit tags</button>
            )}
            {canRemove && m.role !== 'head' && (
              <button
                onClick={() => handleRemove(m)}
                disabled={remove.isPending}
              >
                Remove
              </button>
            )}
          </div>
        </div>
      ))}

      {totalPages > 1 && (
        <p>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>{' '}
          Page {page} of {totalPages}{' '}
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </p>
      )}
    </section>
  )
}
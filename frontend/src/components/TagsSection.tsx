import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { errorMessage } from '../api/errorMessage'
import {
  createTag,
  deleteTag,
  listTags,
  renameTag,
  type Tag,
} from '../api/members'
import { useCan, useRoom } from '../room/useRoom'

export function TagsSection() {
  const { room, refreshRoom } = useRoom()
  const canManage = useCan('tag.manage')
  const queryClient = useQueryClient()
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')

  const tags = useQuery({
    queryKey: ['tags', room.id],
    queryFn: () => listTags(room.id),
  })

  // Tag changes also change the chips on member rows, so refresh both.
  function refreshLists() {
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: ['tags', room.id] }),
      queryClient.invalidateQueries({ queryKey: ['members', room.id] }),
    ])
  }

  function onError(err: unknown) {
    if (err instanceof ApiError && err.status === 403) refreshRoom()
  }

  const create = useMutation({
    mutationFn: (name: string) => createTag(room.id, name),
    onSuccess: async () => {
      setNewName('')
      await refreshLists()
    },
    onError,
  })

  const rename = useMutation({
    mutationFn: (vars: { tagId: string; name: string }) =>
      renameTag(room.id, vars.tagId, vars.name),
    onSuccess: async () => {
      setEditingId(null)
      await refreshLists()
    },
    onError,
  })

  const remove = useMutation({
    mutationFn: (tagId: string) => deleteTag(room.id, tagId),
    onSuccess: refreshLists,
    onError,
  })

  const actionError = create.error ?? rename.error ?? remove.error

  function handleCreate(e: FormEvent) {
    e.preventDefault()
    create.mutate(newName.trim())
  }

  function startEdit(tag: Tag) {
    setEditingId(tag.id)
    setEditName(tag.name)
  }

  function handleRename(e: FormEvent) {
    e.preventDefault()
    if (editingId) rename.mutate({ tagId: editingId, name: editName.trim() })
  }

  function handleDelete(tag: Tag) {
    const ok = window.confirm(
      `Delete the tag "${tag.name}"? It will be removed from ${tag.member_count} member(s).`,
    )
    if (ok) remove.mutate(tag.id)
  }

  let list
  if (tags.isPending) {
    list = <p>Loading tags...</p>
  } else if (tags.isError) {
    list = <p>Could not load tags.</p>
  } else if (tags.data.items.length === 0) {
    list = <p>No tags yet.</p>
  } else {
    list = tags.data.items.map((tag) => (
      <div className="row" key={tag.id}>
        {editingId === tag.id ? (
          <form className="inline-form" onSubmit={handleRename}>
            <input
              aria-label="Tag name"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              maxLength={50}
              required
            />
            <button type="submit" disabled={rename.isPending}>
              Save
            </button>
            <button type="button" onClick={() => setEditingId(null)}>
              Cancel
            </button>
          </form>
        ) : (
          <>
            <div>
              <span className="chip">{tag.name}</span>
              <span className="muted">{tag.member_count} member(s)</span>
            </div>
            {canManage && (
              <div className="actions">
                <button onClick={() => startEdit(tag)}>Rename</button>
                <button onClick={() => handleDelete(tag)}>Delete</button>
              </div>
            )}
          </>
        )}
      </div>
    ))
  }

  return (
    <section>
      <h2>Tags</h2>

      {actionError != null && (
        <div className="form-error">{errorMessage(actionError)}</div>
      )}

      {canManage && (
        <form className="inline-form" onSubmit={handleCreate}>
          <input
            aria-label="New tag name"
            placeholder="New tag, e.g. Video Editor"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            maxLength={50}
            required
          />
          <button type="submit" disabled={create.isPending}>
            Add tag
          </button>
        </form>
      )}

      {list}
    </section>
  )
}
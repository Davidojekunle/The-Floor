import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  createTag,
  deleteTag,
  listMembers,
  listTags,
  removeMember,
  renameTag,
  revokeTempHead,
  setMemberTags,
  type Member,
  type Tag,
} from '../api/members'
import { useAuth } from '../auth/useAuth'
import { Avatar } from '../components/Avatar'
import { ConfirmDialog, Dialog } from '../components/Dialog'
import { Icon } from '../components/Icon'
import { Menu, type MenuItem } from '../components/Menu'
import { useToast } from '../components/toastContext'
import { formatDay } from '../lib/dates'
import { plural, roleLabel } from '../lib/labels'
import { useTimezone } from '../lib/useTimezone'
import { useCan, useRoom } from '../room/roomContext'
import { TransferHeadDialog } from '../room/RoomLifecycle'
import { TempHeadDialog } from '../room/TempHeadDialog'
import { useRoomError } from '../room/useRoomError'

type Open =
  | { kind: 'tags'; member: Member }
  | { kind: 'remove'; member: Member }
  | { kind: 'tempHead'; member: Member }
  | { kind: 'endTempHead'; member: Member }
  | { kind: 'transfer'; member: Member }
  | { kind: 'newTag' }
  | { kind: 'renameTag'; tag: Tag }
  | { kind: 'deleteTag'; tag: Tag }
  | null

export function MembersPage() {
  const { room, refreshRoom } = useRoom()
  const { user } = useAuth()
  const canTag = useCan('tag.manage')
  const canRemove = useCan('member.remove')
  const canTransfer = useCan('head.transfer')
  const canInvite = useCan('invite.manage')
  const canTempHead = useCan('tempHead.manage')
  const tz = useTimezone()
  const queryClient = useQueryClient()
  const toast = useToast()
  const onError = useRoomError()
  const [tab, setTab] = useState<'people' | 'tags'>('people')
  const [open, setOpen] = useState<Open>(null)

  const members = useQuery({ queryKey: ['members', room.id], queryFn: () => listMembers(room.id) })
  const tags = useQuery({ queryKey: ['tags', room.id], queryFn: () => listTags(room.id) })

  const refreshPeople = () => {
    void queryClient.invalidateQueries({ queryKey: ['members', room.id] })
    void queryClient.invalidateQueries({ queryKey: ['tags', room.id] })
  }

  const remove = useMutation({
    mutationFn: (m: Member) => removeMember(room.id, m.membership_id),
    onSuccess: (_, m) => {
      refreshPeople()
      refreshRoom()
      setOpen(null)
      toast(`${m.user.name} was removed from ${room.name}.`)
    },
    onError: (err) => toast(onError(err)),
  })

  const endTempHead = useMutation({
    mutationFn: (m: Member) => revokeTempHead(room.id, m.membership_id),
    onSuccess: (_, m) => {
      refreshPeople()
      setOpen(null)
      toast(`${m.user.name.split(' ')[0]} is a member again.`)
    },
    onError: (err) => toast(onError(err)),
  })

  const removeTagMutation = useMutation({
    mutationFn: (t: Tag) => deleteTag(room.id, t.id),
    onSuccess: (_, t) => {
      refreshPeople()
      void queryClient.invalidateQueries({ queryKey: ['tasks', room.id] })
      setOpen(null)
      toast(`Tag "${t.name}" deleted.`)
    },
    onError: (err) => toast(onError(err)),
  })

  const memberList = members.data?.items ?? []
  const tagList = tags.data?.items ?? []

  const action =
    tab === 'people'
      ? canInvite && (
          <Link className="btn" to={`/rooms/${room.id}/settings`}>
            Invite people
          </Link>
        )
      : canTag && (
          <button className="btn primary" type="button" onClick={() => setOpen({ kind: 'newTag' })}>
            <Icon name="plus" />
            New tag
          </button>
        )

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Members</h1>
          <p className="sub">
            {plural(room.member_count, 'person', 'people')} in {room.name}
          </p>
        </div>
        {action}
      </div>

      <div className="section">
        <div className="seg" role="tablist" aria-label="Members and tags" style={{ justifySelf: 'start' }}>
          <button type="button" role="tab" aria-selected={tab === 'people'} onClick={() => setTab('people')}>
            People · {memberList.length || room.member_count}
          </button>
          <button type="button" role="tab" aria-selected={tab === 'tags'} onClick={() => setTab('tags')}>
            Tags · {tagList.length}
          </button>
        </div>

        <div className="list">
          {tab === 'people' &&
            (members.isPending ? (
              <div className="empty">
                <p>Loading people…</p>
              </div>
            ) : (
              memberList.map((m) => {
                const items: MenuItem[] = []
                if (canTag) items.push({ label: 'Edit tags', onSelect: () => setOpen({ kind: 'tags', member: m }) })
                if (canTempHead && m.role !== 'head') {
                  if (m.role === 'temp_head') {
                    items.push({ label: 'Change end date', onSelect: () => setOpen({ kind: 'tempHead', member: m }) })
                    items.push({ label: 'End temporary head', onSelect: () => setOpen({ kind: 'endTempHead', member: m }) })
                  } else items.push({ label: 'Make temporary head', onSelect: () => setOpen({ kind: 'tempHead', member: m }) })
                }
                if (canTransfer && m.role !== 'head')
                  items.push({ label: 'Make head', onSelect: () => setOpen({ kind: 'transfer', member: m }) })
                if (canRemove && m.role !== 'head')
                  items.push('divider', { label: 'Remove from room', danger: true, onSelect: () => setOpen({ kind: 'remove', member: m }) })
                return (
                  <div className="row" key={m.membership_id}>
                    <Avatar name={m.user.name} />
                    <div className="main">
                      <div className="title">
                        {m.user.name}
                        {m.user.id === user?.id && <span className="faint" style={{ fontWeight: 400 }}> (you)</span>}
                      </div>
                      <div className="meta">
                        {m.role !== 'member' && (
                          <span className="role">
                            {roleLabel(m.role)}
                            {m.role === 'temp_head' && m.temp_head_expires_at && ` · until ${formatDay(m.temp_head_expires_at, tz)}`}
                          </span>
                        )}
                        {m.tags.map((t) => (
                          <span className="tag" key={t.id}>
                            {t.name}
                          </span>
                        ))}
                        {m.role === 'member' && m.tags.length === 0 && <span className="faint">No tags</span>}
                      </div>
                    </div>
                    {items.length > 0 && <Menu label={`Actions for ${m.user.name}`} items={items} />}
                  </div>
                )
              })
            ))}

          {tab === 'tags' &&
            (tagList.length === 0 ? (
              <div className="empty">
                <h2>No tags yet</h2>
                <p>Tags describe what people do here, like Editor or Designer. A stage can go to everyone with a tag.</p>
              </div>
            ) : (
              tagList.map((t) => (
                <div className="row" key={t.id}>
                  <div className="main">
                    <div className="title">{t.name}</div>
                    <div className="meta">{plural(t.member_count, 'person', 'people')}</div>
                  </div>
                  {canTag && (
                    <Menu
                      label={`Actions for ${t.name}`}
                      items={[
                        { label: 'Rename', onSelect: () => setOpen({ kind: 'renameTag', tag: t }) },
                        'divider',
                        { label: 'Delete tag', danger: true, onSelect: () => setOpen({ kind: 'deleteTag', tag: t }) },
                      ]}
                    />
                  )}
                </div>
              ))
            ))}
        </div>
        {tab === 'tags' && !canTag && <p className="faint small">Only the room's head can create and assign tags.</p>}
      </div>

      {open?.kind === 'tags' && (
        <EditTagsDialog member={open.member} tags={tagList} onClose={() => setOpen(null)} onSaved={refreshPeople} />
      )}
      {open?.kind === 'remove' && (
        <ConfirmDialog
          title={`Remove ${open.member.user.name}?`}
          body={`They'll lose access to ${room.name} straight away. Their tags are cleared and they're taken off their stages.${open.member.role === 'temp_head' ? ' Their temporary head role ends too.' : ''} They can ask to join again with the invite link.`}
          confirmLabel="Remove"
          pending={remove.isPending}
          onConfirm={() => remove.mutate(open.member)}
          onClose={() => setOpen(null)}
        />
      )}
      {open?.kind === 'transfer' && <TransferHeadDialog initial={open.member} onClose={() => setOpen(null)} />}
      {open?.kind === 'tempHead' && <TempHeadDialog member={open.member} onClose={() => setOpen(null)} onSaved={refreshPeople} />}
      {open?.kind === 'endTempHead' && (
        <ConfirmDialog
          title={`End ${open.member.user.name.split(' ')[0]}'s temporary head role?`}
          body="They go back to being a member straight away. Anything they did as temporary head stays."
          confirmLabel="End now"
          pending={endTempHead.isPending}
          onConfirm={() => endTempHead.mutate(open.member)}
          onClose={() => setOpen(null)}
        />
      )}
      {(open?.kind === 'newTag' || open?.kind === 'renameTag') && (
        <TagNameDialog tag={open.kind === 'renameTag' ? open.tag : null} onClose={() => setOpen(null)} onSaved={refreshPeople} />
      )}
      {open?.kind === 'deleteTag' && (
        <ConfirmDialog
          title={`Delete "${open.tag.name}"?`}
          body={`${open.tag.member_count === 1 ? '1 person loses' : `${open.tag.member_count} people lose`} this tag. Stages that used it stay, but no longer go to a tag.`}
          confirmLabel="Delete tag"
          pending={removeTagMutation.isPending}
          onConfirm={() => removeTagMutation.mutate(open.tag)}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  )
}

function EditTagsDialog({ member, tags, onClose, onSaved }: { member: Member; tags: Tag[]; onClose: () => void; onSaved: () => void }) {
  const { room } = useRoom()
  const toast = useToast()
  const onError = useRoomError()
  const [picked, setPicked] = useState(() => new Set(member.tags.map((t) => t.id)))

  const save = useMutation({
    mutationFn: () => setMemberTags(room.id, member.membership_id, [...picked]),
    onSuccess: () => {
      onSaved()
      onClose()
      toast(`Tags updated for ${member.user.name}.`)
    },
    onError: (err) => toast(onError(err)),
  })

  return (
    <Dialog
      title={`Tags for ${member.user.name}`}
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" onClick={() => save.mutate()} disabled={save.isPending}>
            Save
          </button>
        </>
      }
    >
      {tags.length === 0 ? (
        <p className="muted">This room has no tags yet. Create one on the Tags tab first.</p>
      ) : (
        <>
          <p className="muted small">Pick any number. Stages assigned to a tag reach everyone who has it.</p>
          <div className="checks">
            {tags.map((t) => (
              <label className="check" key={t.id}>
                <input
                  type="checkbox"
                  checked={picked.has(t.id)}
                  onChange={(e) =>
                    setPicked((prev) => {
                      const next = new Set(prev)
                      if (e.target.checked) next.add(t.id)
                      else next.delete(t.id)
                      return next
                    })
                  }
                />
                <span>{t.name}</span>
              </label>
            ))}
          </div>
        </>
      )}
    </Dialog>
  )
}

function TagNameDialog({ tag, onClose, onSaved }: { tag: Tag | null; onClose: () => void; onSaved: () => void }) {
  const { room } = useRoom()
  const toast = useToast()
  const onError = useRoomError()
  const [name, setName] = useState(tag?.name ?? '')
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: (value: string) => (tag ? renameTag(room.id, tag.id, value) : createTag(room.id, value)),
    onSuccess: (saved) => {
      onSaved()
      onClose()
      toast(tag ? 'Tag renamed.' : `Tag "${saved.name}" created.`)
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) setError(`There's already a tag called "${name.trim()}".`)
      else if (err instanceof ApiError && err.code === 'VALIDATION_ERROR') setError('Use 1 to 50 characters.')
      else setError(onError(err))
    },
  })

  const submit = () => {
    const value = name.trim().replace(/\s+/g, ' ')
    if (!value) return setError('Give the tag a name.')
    save.mutate(value)
  }

  return (
    <Dialog
      title={tag ? 'Rename tag' : 'New tag'}
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" type="button" onClick={submit} disabled={save.isPending}>
            {tag ? 'Save' : 'Create tag'}
          </button>
        </>
      }
    >
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <label htmlFor="tag-name">Name</label>
        <input
          className="input"
          id="tag-name"
          maxLength={50}
          autoFocus
          placeholder="e.g. Colourist"
          value={name}
          onChange={(e) => {
            setName(e.target.value)
            setError(null)
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? 'tag-name-err' : undefined}
        />
        {error && (
          <span className="err" id="tag-name-err" role="alert">
            {error}
          </span>
        )}
      </form>
    </Dialog>
  )
}

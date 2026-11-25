import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { addAdmin, getAdminLog, listAdmins, removeAdmin, type AdminEvent, type AdminPerson } from '../api/admin'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { ConfirmDialog } from '../components/Dialog'
import { useToast } from '../components/toastContext'
import { relativeTime } from '../lib/dates'
import { useTimezone } from '../lib/useTimezone'

const SWITCHES: Record<string, string> = {
  calls: 'Calls',
  signups_open: 'New sign-ups',
  notification_emails: 'Notification emails',
  daily_digest: 'Daily summary',
  push: 'Push notifications',
  announcement: 'Announcement',
  task_assistant: 'Task assistant',
  direct_messages: 'Private messages',
}

function show(key: string | undefined, v: unknown): string {
  if (v === true) return 'on'
  if (v === false) return 'off'
  if (v === null || v === undefined || v === '') return key === 'announcement' ? 'none' : 'unset'
  if (key === 'calls' || key === 'task_assistant' || key === 'direct_messages') return v === 'staff' ? 'staff only' : String(v)
  return key === 'announcement' ? `"${String(v)}"` : String(v)
}

function describe(e: AdminEvent): string {
  if (e.action === 'admin_added') return `made ${e.detail.name} (${e.detail.email}) an admin`
  if (e.action === 'admin_removed') return `removed ${e.detail.name} (${e.detail.email}) as an admin`
  const k = e.detail.key
  const name = SWITCHES[k ?? ''] ?? k
  if (typeof e.detail.new === 'boolean') return `turned ${name} ${e.detail.new ? 'on' : 'off'}`
  return `changed ${name} from ${show(k, e.detail.old)} to ${show(k, e.detail.new)}`
}

/** Admins (the owner adds and removes them) and the change log (every admin sees it). */
export function AdminPeople() {
  const { user, refreshUser } = useAuth()
  const owner = !!user?.is_owner
  const toast = useToast()
  const tz = useTimezone()
  const queryClient = useQueryClient()
  const admins = useQuery({ queryKey: ['admins'], queryFn: listAdmins })
  const log = useQuery({ queryKey: ['admin-log'], queryFn: getAdminLog, refetchInterval: 30_000 })
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [removing, setRemoving] = useState<AdminPerson | null>(null)

  const done = (list: AdminPerson[]) => {
    queryClient.setQueryData(['admins'], list)
    void queryClient.invalidateQueries({ queryKey: ['admin-log'] })
    void refreshUser().catch(() => {})
  }
  const add = useMutation({
    mutationFn: () => addAdmin(email.trim()),
    onSuccess: (list) => {
      done(list)
      toast(`${email.trim()} is now an admin.`)
      setEmail('')
      setError(null)
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Couldn't add them. Try again."),
  })
  const remove = useMutation({
    mutationFn: (p: AdminPerson) => removeAdmin(p.id),
    onSuccess: (list, p) => {
      done(list)
      setRemoving(null)
      toast(`${p.name} is no longer an admin.`)
    },
    onError: (e) => {
      setRemoving(null)
      toast(e instanceof ApiError ? e.message : "Couldn't remove them. Try again.")
    },
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    if (email.trim()) add.mutate()
  }

  return (
    <>
      <section className="admin-sec" aria-labelledby="adm-admins">
        <h2 id="adm-admins">Admins</h2>
        <p className="faint small">
          {owner ? 'Admins can open this page and change the switches. Only you can add or remove them.' : 'Only the owner can add or remove admins.'}
        </p>
        <ul className="admin-people">
          {admins.data?.map((p) => (
            <li key={p.id}>
              <span>
                {p.name} <span className="faint small">{p.email}</span>
                {p.is_owner && <span className="badge">Owner</span>}
              </span>
              {owner && !p.is_owner && (
                <button type="button" className="link-btn danger-text" onClick={() => setRemoving(p)}>
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
        {owner && (
          <form className="admin-add" onSubmit={submit}>
            <label className="sr-only" htmlFor="admin-email">
              Email of the account to make an admin
            </label>
            <input
              id="admin-email"
              type="email"
              placeholder="Their account email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={add.isPending}
            />
            <button type="submit" className="btn" disabled={add.isPending || !email.trim()}>
              {add.isPending ? 'Adding…' : 'Make admin'}
            </button>
            {error && (
              <p className="err small" role="alert">
                {error}
              </p>
            )}
          </form>
        )}
      </section>

      <section className="admin-sec" aria-labelledby="adm-log">
        <h2 id="adm-log">Change log</h2>
        {log.data?.length ? (
          <ol className="admin-log">
            {log.data.map((e) => (
              <li key={e.id}>
                <span>
                  <strong>{e.actor_name}</strong> {describe(e)}
                </span>
                <span className="faint small">{relativeTime(e.created_at, tz)}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="faint small">Nothing yet. Switches turned on or off and admins added or removed show up here.</p>
        )}
      </section>

      {removing && (
        <ConfirmDialog
          title={`Remove ${removing.name} as an admin?`}
          body="They'll lose access to this page and its switches straight away. Their account and rooms stay as they are."
          confirmLabel="Remove admin"
          pending={remove.isPending}
          onConfirm={() => remove.mutate(removing)}
          onClose={() => setRemoving(null)}
        />
      )}
    </>
  )
}

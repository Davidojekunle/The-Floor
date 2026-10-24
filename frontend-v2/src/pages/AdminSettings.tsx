import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { getSiteSettings, updateSiteSettings, type SiteSettings } from '../api/admin'
import { useAuth } from '../auth/useAuth'
import { ConfirmDialog } from '../components/Dialog'
import { Switch } from '../components/Switch'
import { useToast } from '../components/toastContext'

type Pending = { change: Partial<SiteSettings>; title: string; body: string; label: string }

const CALLS: { value: SiteSettings['calls']; label: string }[] = [
  { value: 'off', label: 'Off' },
  { value: 'staff', label: 'Staff only' },
  { value: 'everyone', label: 'Everyone' },
]

/** Staff: site-wide switches. Each takes effect at once; the big ones ask first. */
export function AdminSettings() {
  const toast = useToast()
  const { refreshUser } = useAuth()
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['site-settings'], queryFn: getSiteSettings })
  const [pending, setPending] = useState<Pending | null>(null)
  const [draft, setDraft] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: (change: Partial<SiteSettings>) => updateSiteSettings(change),
    onSuccess: (s) => {
      queryClient.setQueryData(['site-settings'], s)
      void queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
      void queryClient.invalidateQueries({ queryKey: ['site'] })
      void refreshUser().catch(() => {}) // calls on or off for me, the banner
      setPending(null)
      toast('Saved. It applies to everyone now.')
    },
    onError: (e) => {
      setPending(null)
      toast(e instanceof ApiError ? e.message : "Couldn't save. Try again.")
    },
  })

  if (!settings.data) return null
  const s = settings.data
  const ask = (p: Pending) => setPending(p)

  const setCalls = (mode: SiteSettings['calls']) => {
    if (mode === s.calls) return
    if (mode === 'everyone')
      ask({
        change: { calls: mode },
        title: 'Turn on calls for everyone?',
        body: 'Every room gets Start a call, the Calls page and meetings. Each call uses free LiveKit minutes (5,000 a month).',
        label: 'Turn on for everyone',
      })
    else save.mutate({ calls: mode })
  }
  const toggle = (key: 'signups_open' | 'notification_emails' | 'daily_digest' | 'push', on: boolean, off: Omit<Pending, 'change'>) =>
    on ? save.mutate({ [key]: true }) : ask({ change: { [key]: false }, ...off })
  const announcement = draft ?? s.announcement ?? ''

  return (
    <section className="admin-sec" aria-labelledby="adm-switches">
      <h2 id="adm-switches">Site switches</h2>
      <div className="admin-switches">
        <div className="admin-switch-row">
          <div>
            <strong>Calls and meetings</strong>
            <div className="faint small">
              {s.calls_ready
                ? 'Staff only lets you test on the live site before anyone else sees calls.'
                : "LiveKit isn't set up on this server yet: add LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET in Render."}
            </div>
          </div>
          <div className="seg" role="radiogroup" aria-label="Calls and meetings">
            {CALLS.map((c) => (
              <button key={c.value} type="button" role="radio" aria-checked={s.calls === c.value}
                disabled={save.isPending || (!s.calls_ready && c.value !== 'off')} onClick={() => setCalls(c.value)}>
                {c.label}
              </button>
            ))}
          </div>
        </div>
        <Switch
          label="New sign-ups"
          detail="Closed: only people a room invited by email can make an account."
          checked={s.signups_open}
          disabled={save.isPending}
          onChange={(v) => toggle('signups_open', v, { title: 'Close sign-ups?', body: 'Nobody new can make an account, except people a room has invited by email.', label: 'Close sign-ups' })}
        />
        <Switch
          label="Notification emails"
          detail="Requests, decisions, work, mentions, meetings and the daily digest. Security emails (password resets, confirmations) always go."
          checked={s.notification_emails}
          disabled={save.isPending}
          onChange={(v) => toggle('notification_emails', v, { title: 'Pause notification emails?', body: 'Nobody gets notification or meeting emails until you turn them back on. The bell keeps working, and security emails still go.', label: 'Pause emails' })}
        />
        <Switch
          label="Daily summary email"
          detail="The 8:00 digest of what's due, overdue and waiting."
          checked={s.daily_digest}
          disabled={save.isPending || !s.notification_emails}
          onChange={(v) => toggle('daily_digest', v, { title: 'Pause the daily summary?', body: 'Nobody gets the 8:00 summary until you turn it back on.', label: 'Pause it' })}
        />
        <Switch
          label="Push notifications"
          detail="Pop-ups on phones and computers."
          checked={s.push}
          disabled={save.isPending}
          onChange={(v) => toggle('push', v, { title: 'Pause push notifications?', body: 'No pop-ups on anyone’s devices until you turn them back on. The bell keeps working.', label: 'Pause push' })}
        />
        <div className="admin-announce">
          <label htmlFor="adm-announce">
            <strong>Announcement</strong>
            <span className="faint small"> A banner for everyone signed in, e.g. "New: video calls in your rooms". Leave empty for none.</span>
          </label>
          <div className="invite-field">
            <input className="input" id="adm-announce" maxLength={300} value={announcement} placeholder="No announcement"
              onChange={(e) => setDraft(e.target.value)} />
            <button className="btn" type="button" disabled={save.isPending || announcement.trim() === (s.announcement ?? '')}
              onClick={() => { save.mutate({ announcement: announcement.trim() || null }); setDraft(null) }}>
              {announcement.trim() ? 'Show it' : 'Clear it'}
            </button>
          </div>
        </div>
      </div>
      {pending && (
        <ConfirmDialog
          title={pending.title}
          body={pending.body}
          confirmLabel={pending.label}
          pending={save.isPending}
          onClose={() => setPending(null)}
          onConfirm={() => save.mutate(pending.change)}
        />
      )}
    </section>
  )
}

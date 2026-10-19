import { useState, type FormEvent, type ReactNode } from 'react'
import { useMutation } from '@tanstack/react-query'
import { cancelEmailChange, changeEmail, changePassword, updateMe, type Theme } from '../api/auth'
import { ApiError } from '../api/client'
import { acceptToken } from '../auth/session'
import { useAuth } from '../auth/useAuth'
import { ConfirmDialog } from '../components/Dialog'
import { PushSwitch } from '../components/PushSwitch'
import { Switch } from '../components/Switch'
import { useNotificationSettings } from '../room/useNotificationSettings'
import { useToast } from '../components/toastContext'
import { applyTheme } from '../lib/theme'

const THEMES: { value: Theme; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

/** A field-level message from an ApiError, or the general message. */
function fieldOr(err: unknown, field: string): { field?: string; form?: string } {
  if (err instanceof ApiError && err.fields?.[field]) return { field: err.fields[field] }
  if (err instanceof ApiError && err.code === 'INVALID_CREDENTIALS' && field === 'current_password') return { field: 'Incorrect password.' }
  return { form: err instanceof Error ? err.message : 'Something went wrong. Try again.' }
}

/** Your account (L3): profile, appearance, email, password, and signing out everywhere. Each section saves on its own. */
export function AccountPage() {
  const { user } = useAuth()
  if (!user) return null
  return (
    <div className="container">
    <div className="page narrow account">
      <div className="page-head">
        <div>
          <h1>Account</h1>
          <p className="sub">{user.email}</p>
        </div>
      </div>
      <ProfileSection />
      <AppearanceSection />
      <NotificationsSection />
      <EmailSection />
      <PasswordSection />
      <SessionsSection />
    </div>
    </div>
  )
}

function Section({ title, sub, children }: { title: string; sub?: ReactNode; children: ReactNode }) {
  const id = `sec-${title.toLowerCase().replace(/\W+/g, '-')}`
  return (
    <section className="form-card" aria-labelledby={id}>
      <div>
        <h2 id={id}>{title}</h2>
        {sub && (
          <p className="muted small" style={{ marginTop: 4 }}>
            {sub}
          </p>
        )}
      </div>
      {children}
    </section>
  )
}

function ProfileSection() {
  const { user, setMe } = useAuth()
  const toast = useToast()
  const [name, setName] = useState(user!.name)
  const [timezone, setTimezone] = useState(user!.timezone)
  const [error, setError] = useState<{ name?: string; timezone?: string; form?: string }>({})
  const zones = Intl.supportedValuesOf('timeZone')
  const changed = name.trim() !== user!.name || timezone !== user!.timezone

  const save = useMutation({
    mutationFn: () =>
      updateMe({ ...(name.trim() !== user!.name ? { name: name.trim() } : {}), ...(timezone !== user!.timezone ? { timezone } : {}) }),
    onSuccess: (me) => {
      setMe(me)
      toast('Profile saved.')
    },
    onError: (err) => {
      const n = fieldOr(err, 'name')
      const t = fieldOr(err, 'timezone')
      setError({ name: n.field, timezone: t.field, form: n.form && t.form ? n.form : undefined })
    },
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return setError({ name: 'Your name can’t be empty.' })
    save.mutate()
  }

  return (
    <Section title="Profile" sub="Your name is what people in your rooms see.">
      <form className="account-form" onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="acc-name">Name</label>
          <input
            className="input"
            id="acc-name"
            autoComplete="name"
            maxLength={100}
            value={name}
            aria-invalid={error.name ? true : undefined}
            onChange={(e) => {
              setName(e.target.value)
              setError({})
            }}
          />
          {error.name && (
            <span className="err" role="alert">
              {error.name}
            </span>
          )}
        </div>
        <div className="field">
          <label htmlFor="acc-tz">Time zone</label>
          <select className="select" id="acc-tz" value={timezone} onChange={(e) => setTimezone(e.target.value)}>
            {(zones.includes(timezone) ? zones : [timezone, ...zones]).map((z) => (
              <option key={z} value={z}>
                {z.replaceAll('_', ' ')}
              </option>
            ))}
          </select>
          {error.timezone ? (
            <span className="err" role="alert">
              {error.timezone}
            </span>
          ) : (
            <span className="hint">Due dates end at midnight here, and your daily summary arrives at 8:00.</span>
          )}
        </div>
        {error.form && (
          <div className="form-error" role="alert">
            {error.form}
          </div>
        )}
        <div className="form-foot">
          <button className="btn primary" type="submit" disabled={!changed || save.isPending}>
            {save.isPending ? 'Saving…' : 'Save profile'}
          </button>
        </div>
      </form>
    </Section>
  )
}

function AppearanceSection() {
  const { user, setMe } = useAuth()
  const toast = useToast()
  const [theme, setTheme] = useState<Theme>(user!.theme ?? 'system')
  const save = useMutation({
    mutationFn: (t: Theme) => updateMe({ theme: t }),
    onSuccess: (me) => setMe(me),
    onError: (err, t) => {
      // Put it back the way the account has it.
      const previous = user!.theme ?? 'system'
      if (previous !== t) {
        setTheme(previous)
        applyTheme(previous)
      }
      toast(err instanceof Error ? err.message : "Couldn't save the theme.")
    },
  })
  const pick = (t: Theme) => {
    setTheme(t)
    applyTheme(t) // at once; saving follows
    save.mutate(t)
  }
  return (
    <Section title="Appearance" sub="Follows you on every device you sign in on. System matches your device's setting.">
      <div className="seg theme-seg" role="radiogroup" aria-label="Theme">
        {THEMES.map((t) => (
          <button key={t.value} type="button" role="radio" aria-checked={theme === t.value} aria-pressed={theme === t.value} onClick={() => pick(t.value)}>
            {t.label}
          </button>
        ))}
      </div>
    </Section>
  )
}

function NotificationsSection() {
  const { settings, isPending, update } = useNotificationSettings()
  if (isPending || !settings) return null
  const off = !settings.email_enabled
  const muted = settings.muted_rooms.length
  return (
    <Section
      title="Notifications"
      sub={
        <>
          The bell in the app always shows everything. These choose what also reaches you by email and as pop-ups on your
          devices. Security emails (password and email changes) always go.
          {muted > 0 && ` ${muted === 1 ? 'One room is' : `${muted} rooms are`} muted; change that in each room's Settings.`}
        </>
      }
    >
      <div className="switch-list">
        <PushSwitch />
        <Switch
          label="Send me emails"
          detail="Turn off to keep everything in the app and on your devices."
          checked={settings.email_enabled}
          onChange={(v) => update({ email_enabled: v })}
        />
      </div>
      <h3 className="switch-head">Tell me about</h3>
      <div className="switch-list">
        <Switch
          label="Requests"
          detail="Someone asks to join, a task is proposed, or stages are left with nobody."
          checked={settings.requests}
          onChange={(v) => update({ requests: v })}
        />
        <Switch
          label="Decisions"
          detail="Your requests and proposals are answered, or your role changes."
          checked={settings.decisions}
          onChange={(v) => update({ decisions: v })}
        />
        <Switch
          label="Work for you"
          detail="A stage is ready for you, or you're assigned to one."
          checked={settings.assignments}
          onChange={(v) => update({ assignments: v })}
        />
        <Switch
          label="Mentions"
          detail="Someone @mentions you in a room's chat."
          checked={settings.mentions}
          onChange={(v) => update({ mentions: v })}
        />
        <Switch
          label="Every chat message"
          detail="A pop-up on your devices for each new message in your rooms, not just mentions. No emails."
          checked={settings.all_messages}
          onChange={(v) => update({ all_messages: v })}
        />
        <Switch
          label="Daily summary email"
          detail="At 8:00 your time: what's due, overdue or blocked, and what's waiting on you."
          checked={settings.daily_digest}
          disabled={off}
          onChange={(v) => update({ daily_digest: v })}
        />
      </div>
    </Section>
  )
}

function EmailSection() {
  const { user, setMe, refreshUser } = useAuth()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<{ new_email?: string; current_password?: string; form?: string }>({})
  const pending = user!.pending_email

  const request = useMutation({
    mutationFn: () => changeEmail(email.trim(), password),
    onSuccess: async () => {
      setOpen(false)
      setPassword('')
      toast(`Check ${email.trim()} for a link to confirm it.`)
      await refreshUser()
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === 'INVALID_CREDENTIALS') return setError({ current_password: 'Incorrect password.' })
      if (err instanceof ApiError && err.fields?.new_email) return setError({ new_email: err.fields.new_email })
      setError({ form: err instanceof Error ? err.message : 'Something went wrong.' })
    },
  })
  const cancel = useMutation({
    mutationFn: cancelEmailChange,
    onSuccess: async () => {
      setMe({ ...user!, pending_email: null })
      toast('Email change cancelled.')
      await refreshUser()
    },
    onError: (err) => toast(err instanceof Error ? err.message : 'Something went wrong.'),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const next = {
      new_email: /^\S+@\S+\.\S+$/.test(email.trim()) ? undefined : 'Enter an email address.',
      current_password: password ? undefined : 'Enter your current password.',
    }
    setError(next)
    if (!next.new_email && !next.current_password) request.mutate()
  }

  return (
    <Section title="Email" sub={<>You sign in with <strong>{user!.email}</strong>.</>}>
      {pending && (
        <div className="notice pending-email" role="status">
          <span>
            Waiting for you to confirm <strong>{pending}</strong>. Open the link we sent there. Until then, keep signing in with your
            current email.
          </span>
          <button className="btn sm" type="button" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            Cancel change
          </button>
        </div>
      )}
      {!open ? (
        <div className="form-foot">
          <button className="btn" type="button" onClick={() => setOpen(true)}>
            {pending ? 'Use a different new email' : 'Change email'}
          </button>
        </div>
      ) : (
        <form className="account-form" onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="acc-new-email">New email</label>
            <input
              className="input"
              id="acc-new-email"
              type="email"
              autoComplete="email"
              autoFocus
              value={email}
              aria-invalid={error.new_email ? true : undefined}
              onChange={(e) => {
                setEmail(e.target.value)
                setError({})
              }}
            />
            {error.new_email ? (
              <span className="err" role="alert">
                {error.new_email}
              </span>
            ) : (
              <span className="hint">We'll send a link there. It works for 24 hours, and needs your password to confirm.</span>
            )}
          </div>
          <div className="field">
            <label htmlFor="acc-email-pw">Current password</label>
            <input
              className="input"
              id="acc-email-pw"
              type="password"
              autoComplete="current-password"
              value={password}
              aria-invalid={error.current_password ? true : undefined}
              onChange={(e) => {
                setPassword(e.target.value)
                setError({})
              }}
            />
            {error.current_password && (
              <span className="err" role="alert">
                {error.current_password}
              </span>
            )}
          </div>
          {error.form && (
            <div className="form-error" role="alert">
              {error.form}
            </div>
          )}
          <div className="form-foot">
            <button className="btn ghost" type="button" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button className="btn primary" type="submit" disabled={request.isPending}>
              {request.isPending ? 'Sending…' : 'Send confirmation link'}
            </button>
          </div>
        </form>
      )}
    </Section>
  )
}

function PasswordSection() {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [error, setError] = useState<{ current_password?: string; new_password?: string; again?: string; form?: string }>({})

  const reset = () => {
    setOpen(false)
    setCurrent('')
    setNext('')
    setAgain('')
    setError({})
  }

  const save = useMutation({
    mutationFn: () => changePassword(current, next),
    onSuccess: (res) => {
      acceptToken(res.access_token, res.expires_in) // this tab carries on; every other device is signed out
      reset()
      toast('Password changed. Your other devices were signed out.')
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === 'INVALID_CREDENTIALS') return setError({ current_password: 'Incorrect password.' })
      if (err instanceof ApiError && err.fields?.new_password) return setError({ new_password: err.fields.new_password })
      setError({ form: err instanceof Error ? err.message : 'Something went wrong.' })
    },
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const errs = {
      current_password: current ? undefined : 'Enter your current password.',
      new_password: next.length < 8 ? 'Use at least 8 characters.' : undefined,
      again: next.length >= 8 && again !== next ? "The two passwords don't match." : undefined,
    }
    setError(errs)
    if (!errs.current_password && !errs.new_password && !errs.again) save.mutate()
  }

  const field = (id: string, label: string, value: string, set: (v: string) => void, key: keyof typeof error, auto: string, hint?: string) => (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        className="input"
        id={id}
        type="password"
        autoComplete={auto}
        value={value}
        aria-invalid={error[key] ? true : undefined}
        onChange={(e) => {
          set(e.target.value)
          setError({})
        }}
      />
      {error[key] ? (
        <span className="err" role="alert">
          {error[key]}
        </span>
      ) : (
        hint && <span className="hint">{hint}</span>
      )}
    </div>
  )

  return (
    <Section title="Password" sub="Changing it signs you out on every other device. You stay signed in here.">
      {!open ? (
        <div className="form-foot">
          <button className="btn" type="button" onClick={() => setOpen(true)}>
            Change password
          </button>
        </div>
      ) : (
        <form className="account-form" onSubmit={submit} noValidate>
          {field('acc-cur', 'Current password', current, setCurrent, 'current_password', 'current-password')}
          {field('acc-new', 'New password', next, setNext, 'new_password', 'new-password', 'At least 8 characters.')}
          {field('acc-again', 'Type it again', again, setAgain, 'again', 'new-password')}
          {error.form && (
            <div className="form-error" role="alert">
              {error.form}
            </div>
          )}
          <div className="form-foot">
            <button className="btn ghost" type="button" onClick={reset}>
              Cancel
            </button>
            <button className="btn primary" type="submit" disabled={save.isPending}>
              {save.isPending ? 'Saving…' : 'Change password'}
            </button>
          </div>
        </form>
      )}
    </Section>
  )
}

function SessionsSection() {
  const { logoutEverywhere } = useAuth()
  const toast = useToast()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  return (
    <Section title="Signed-in devices" sub="Lost a phone, or used a shared computer? Sign out everywhere, this device included.">
      <div className="form-foot">
        <button className="btn danger-outline" type="button" onClick={() => setConfirming(true)}>
          Sign out everywhere
        </button>
      </div>
      {confirming && (
        <ConfirmDialog
          title="Sign out everywhere?"
          body="Every device signed in to your account is signed out straight away, including this one."
          confirmLabel="Sign out everywhere"
          pending={busy}
          onConfirm={() => {
            setBusy(true)
            logoutEverywhere().catch(() => {
              setBusy(false)
              toast("Couldn't reach The Floor. Try again.")
            })
          }}
          onClose={() => setConfirming(false)}
        />
      )}
    </Section>
  )
}

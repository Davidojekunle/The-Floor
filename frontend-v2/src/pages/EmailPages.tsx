import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { cancelEmailChangeByLink, confirmEmail } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { Logo } from '../components/Logo'

/** Read ?token= once, then take it out of the address bar and history, and don't leak this URL as a referrer. */
function useLinkToken(): string {
  const [token] = useState(() => new URLSearchParams(window.location.search).get('token') ?? '')
  useEffect(() => {
    if (window.location.search) window.history.replaceState(window.history.state, '', window.location.pathname)
    const meta = document.createElement('meta')
    meta.name = 'referrer'
    meta.content = 'no-referrer'
    document.head.appendChild(meta)
    return () => meta.remove()
  }, [])
  return token
}

function Frame({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  return (
    <div className="center-screen">
      <div className="auth">
        <Link to="/" className="auth-home" aria-label="The Floor, home">
          <Logo />
        </Link>
        {children}
        <p className="auth-foot">{user ? <Link to="/account">Go to your account</Link> : <Link to="/login">Sign in</Link>}</p>
      </div>
    </div>
  )
}

function DeadLink({ what }: { what: string }) {
  return (
    <div className="auth-card">
      <div>
        <h1>This link doesn't work any more</h1>
        <p className="muted" style={{ marginTop: 6 }}>
          {what} links work once and expire after 24 hours. They also stop working when a newer change is requested or the
          change is cancelled.
        </p>
      </div>
    </div>
  )
}

/** Opened from the email sent to the NEW address. Needs the account's password, so a mistyped address can't take it. */
export function ConfirmEmailPage() {
  const token = useLinkToken()
  const { user, refreshUser } = useAuth()
  const [password, setPassword] = useState('')
  const [error, setError] = useState<{ password?: string; form?: string }>({})
  const [state, setState] = useState<'form' | 'done' | 'dead'>(token ? 'form' : 'dead')
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!password) return setError({ password: 'Enter the password for this account.' })
    setBusy(true)
    try {
      await confirmEmail(token, password)
      setState('done')
      if (user) void refreshUser()
    } catch (err) {
      if (err instanceof ApiError && err.code === 'EMAIL_TOKEN_INVALID') setState('dead')
      else if (err instanceof ApiError && err.code === 'INVALID_CREDENTIALS') setError({ password: 'Incorrect password.' })
      else if (err instanceof ApiError && err.fields?.new_email) setError({ form: err.fields.new_email })
      else setError({ form: err instanceof Error ? err.message : 'Something went wrong.' })
    } finally {
      setBusy(false)
    }
  }

  if (state === 'dead')
    return (
      <Frame>
        <DeadLink what="Confirmation" />
      </Frame>
    )
  if (state === 'done')
    return (
      <Frame>
        <div className="auth-card">
          <div>
            <h1>Email changed</h1>
            <p className="muted" style={{ marginTop: 6 }}>
              From now on, sign in with this new address. Your old address got a note saying so.
            </p>
          </div>
          {user ? (
            <Link className="btn primary block" to="/account">
              Back to your account
            </Link>
          ) : (
            <Link className="btn primary block" to="/login">
              Sign in
            </Link>
          )}
        </div>
      </Frame>
    )

  return (
    <Frame>
      <form className="auth-card" onSubmit={submit} noValidate>
        <div>
          <h1>Confirm your new email</h1>
          <p className="muted" style={{ marginTop: 4 }}>
            Enter your password to finish. This makes sure it's really your account.
          </p>
        </div>
        {error.form && (
          <div className="form-error" role="alert">
            {error.form}
          </div>
        )}
        <div className="field">
          <label htmlFor="confirm-pw">Password</label>
          <input
            className="input"
            id="confirm-pw"
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            aria-invalid={error.password ? true : undefined}
            onChange={(e) => {
              setPassword(e.target.value)
              setError({})
            }}
          />
          {error.password && (
            <span className="err" role="alert">
              {error.password}
            </span>
          )}
        </div>
        <button className="btn primary block" type="submit" disabled={busy}>
          {busy ? 'Confirming…' : 'Confirm new email'}
        </button>
      </form>
    </Frame>
  )
}

/** Opened from the notice sent to the OLD address: "this wasn't me". Acts only on the button (mail scanners open links). */
export function CancelEmailChangePage() {
  const token = useLinkToken()
  const { user, refreshUser } = useAuth()
  const [state, setState] = useState<'ask' | 'done' | 'dead'>(token ? 'ask' : 'dead')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function cancel() {
    setBusy(true)
    setError(null)
    try {
      await cancelEmailChangeByLink(token)
      setState('done')
      if (user) void refreshUser()
    } catch (err) {
      if (err instanceof ApiError && err.code === 'EMAIL_TOKEN_INVALID') setState('dead')
      else setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  if (state === 'dead')
    return (
      <Frame>
        <DeadLink what="Cancel" />
      </Frame>
    )
  return (
    <Frame>
      <div className="auth-card">
        {state === 'done' ? (
          <div>
            <h1>Change cancelled</h1>
            <p className="muted" style={{ marginTop: 6 }}>
              Your email stays the same. If you didn't ask for the change, someone may know your password: change it now.
            </p>
          </div>
        ) : (
          <div>
            <h1>Cancel the email change?</h1>
            <p className="muted" style={{ marginTop: 6 }}>
              Someone asked to move this account to a new email address. If it wasn't you, cancel it, then change your password.
            </p>
          </div>
        )}
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        {state === 'done' ? (
          <Link className="btn primary block" to={user ? '/account' : '/forgot-password'}>
            {user ? 'Change your password' : 'Reset your password'}
          </Link>
        ) : (
          <button className="btn danger block" type="button" disabled={busy} onClick={() => void cancel()}>
            {busy ? 'Cancelling…' : 'Cancel the change'}
          </button>
        )}
      </div>
    </Frame>
  )
}

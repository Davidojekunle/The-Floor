import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { forgotPassword, resetPassword } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { Logo } from '../components/Logo'

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="center-screen">
      <div className="auth">
        <Link to="/" className="auth-home" aria-label="The Floor, home">
          <Logo />
        </Link>
        {children}
      </div>
    </div>
  )
}

/** "Forgot password?": ask for a link. The answer is the same whether or not the account exists. */
export function ForgotPasswordPage() {
  const location = useLocation()
  const [email, setEmail] = useState((location.state as { email?: string } | null)?.email ?? '')
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const value = email.trim()
    if (!/^\S+@\S+\.\S+$/.test(value)) return setError('Enter the email you sign in with.')
    setBusy(true)
    setError(null)
    try {
      await forgotPassword(value)
      setSentTo(value)
    } catch (err) {
      setError(err instanceof ApiError && err.fields?.email ? 'Enter a valid email address.' : err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  if (sentTo)
    return (
      <Frame>
        <div className="auth-card">
          <div>
            <h1>Check your email</h1>
            <p className="muted" style={{ marginTop: 6 }}>
              If <strong>{sentTo}</strong> has an account, a link to choose a new password is on its way. It works once, for 30
              minutes.
            </p>
          </div>
          <p className="muted small">Nothing there after a few minutes? Check spam, or make sure it's the address you sign in with.</p>
          <button className="btn block" type="button" onClick={() => setSentTo(null)}>
            Use a different email
          </button>
        </div>
        <p className="auth-foot">
          <Link to="/login">Back to sign in</Link>
        </p>
      </Frame>
    )

  return (
    <Frame>
      <form className="auth-card" onSubmit={submit} noValidate>
        <div>
          <h1>Forgot your password?</h1>
          <p className="muted" style={{ marginTop: 4 }}>
            Enter your email and we'll send you a link to choose a new one.
          </p>
        </div>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            className="input"
            id="email"
            type="email"
            autoComplete="email"
            autoFocus
            value={email}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? 'email-err' : undefined}
            onChange={(e) => {
              setEmail(e.target.value)
              setError(null)
            }}
          />
          {error && (
            <span className="err" id="email-err" role="alert">
              {error}
            </span>
          )}
        </div>
        <button className="btn primary block" type="submit" disabled={busy}>
          {busy ? 'Sending…' : 'Send reset link'}
        </button>
      </form>
      <p className="auth-foot">
        Remembered it? <Link to="/login">Sign in</Link>
      </p>
    </Frame>
  )
}

/** Opened from the email: /reset-password?token=… */
export function ResetPasswordPage() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  // Keep the token, then take it out of the address bar and history (it grants access to the account).
  const [token] = useState(() => new URLSearchParams(window.location.search).get('token') ?? '')
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [errors, setErrors] = useState<{ password?: string; again?: string; form?: string }>({})
  const [invalid, setInvalid] = useState(!token)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (window.location.search) window.history.replaceState(window.history.state, '', window.location.pathname)
    // Don't send this page's address to other sites (fonts and so on).
    const meta = document.createElement('meta')
    meta.name = 'referrer'
    meta.content = 'no-referrer'
    document.head.appendChild(meta)
    return () => meta.remove()
  }, [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    const next = {
      password: password.length < 8 ? 'Use at least 8 characters.' : undefined,
      again: password.length >= 8 && again !== password ? "The two passwords don't match." : undefined,
    }
    setErrors(next)
    if (next.password || next.again) return
    setBusy(true)
    try {
      await resetPassword(token, password)
      // Every device is signed out by the reset, this one included.
      if (user) await logout()
      navigate('/login', { replace: true, state: { notice: 'Password changed. Sign in with your new password.' } })
    } catch (err) {
      if (err instanceof ApiError && err.code === 'RESET_TOKEN_INVALID') setInvalid(true)
      else if (err instanceof ApiError && err.fields?.new_password) setErrors({ password: err.fields.new_password })
      else setErrors({ form: err instanceof Error ? err.message : 'Something went wrong.' })
    } finally {
      setBusy(false)
    }
  }

  if (invalid)
    return (
      <Frame>
        <div className="auth-card">
          <div>
            <h1>This link doesn't work any more</h1>
            <p className="muted" style={{ marginTop: 6 }}>
              Reset links work once and expire after 30 minutes. Asking for a new link also cancels older ones.
            </p>
          </div>
          <Link className="btn primary block" to="/forgot-password">
            Send me a new link
          </Link>
        </div>
        <p className="auth-foot">
          <Link to="/login">Back to sign in</Link>
        </p>
      </Frame>
    )

  return (
    <Frame>
      <form className="auth-card" onSubmit={submit} noValidate>
        <div>
          <h1>Choose a new password</h1>
          <p className="muted" style={{ marginTop: 4 }}>
            You'll be signed out on every device, then you can sign in with the new one.
          </p>
        </div>
        {errors.form && (
          <div className="form-error" role="alert">
            {errors.form}
          </div>
        )}
        <div className="field">
          <label htmlFor="new-password">New password</label>
          <input
            className="input"
            id="new-password"
            type="password"
            autoComplete="new-password"
            autoFocus
            value={password}
            aria-invalid={errors.password ? true : undefined}
            onChange={(e) => {
              setPassword(e.target.value)
              setErrors({})
            }}
          />
          {errors.password ? (
            <span className="err" role="alert">
              {errors.password}
            </span>
          ) : (
            <span className="hint">At least 8 characters.</span>
          )}
        </div>
        <div className="field">
          <label htmlFor="again">Type it again</label>
          <input
            className="input"
            id="again"
            type="password"
            autoComplete="new-password"
            value={again}
            aria-invalid={errors.again ? true : undefined}
            onChange={(e) => {
              setAgain(e.target.value)
              setErrors((x) => ({ ...x, again: undefined }))
            }}
          />
          {errors.again && (
            <span className="err" role="alert">
              {errors.again}
            </span>
          )}
        </div>
        <button className="btn primary block" type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Save new password'}
        </button>
      </form>
    </Frame>
  )
}

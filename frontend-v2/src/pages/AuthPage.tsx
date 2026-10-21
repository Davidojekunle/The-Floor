import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { Logo } from '../components/Logo'

type Mode = 'login' | 'register'

// Server validation text is technical, so show our own wording when we recognise the field.
const FRIENDLY: Record<string, string> = {
  email: 'Enter a valid email address.',
  password: 'Use at least 8 characters.',
  name: 'Enter your name.',
}

export function AuthPage({ mode }: { mode: Mode }) {
  const { user, loading, login, register, sessionExpired } = useAuth()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/' // '/' opens the last room
  const notice = (location.state as { notice?: string } | null)?.notice // e.g. after a password reset
  const fromInvite = from.startsWith('/join/') // an invite link sent them here
  const isRegister = mode === 'register'

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)

  if (loading) return null // checking the refresh cookie: don't flash the form at someone who's signed in
  if (user) return <Navigate to={from} replace />

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    setFieldErrors({})
    setSubmitting(true)
    try {
      if (isRegister) {
        await register({
          name,
          email,
          password,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        })
      } else {
        await login(email, password)
      }
      // Navigation happens on the next render, when `user` is set.
    } catch (err) {
      if (!(err instanceof ApiError)) setFormError('Something went wrong. Try again.')
      else if (err.code === 'INVALID_CREDENTIALS') {
        setFormError('Incorrect email or password.')
        setPassword('')
      } else if (err.fields) {
        const mapped: Record<string, string> = {}
        for (const [key, msg] of Object.entries(err.fields)) {
          mapped[key] = err.status === 409 ? msg : (FRIENDLY[key] ?? msg)
        }
        setFieldErrors(mapped)
      } else setFormError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const fieldProps = (key: string) => ({
    'aria-invalid': fieldErrors[key] ? true : undefined,
    'aria-describedby': fieldErrors[key] ? `${key}-err` : undefined,
  })
  const fieldError = (key: string) =>
    fieldErrors[key] ? (
      <span className="err" id={`${key}-err`} role="alert">
        {fieldErrors[key]}
      </span>
    ) : null

  return (
    <div className="center-screen">
      <div className="auth">
        <Link to="/" className="auth-home" aria-label="The Floor, home">
          <Logo />
        </Link>
        <form className="auth-card" onSubmit={handleSubmit} noValidate>
          <div>
            <h1>{isRegister ? 'Create your account' : 'Sign in'}</h1>
            <p className="muted" style={{ marginTop: 4 }}>
              {fromInvite
                ? `${isRegister ? 'Create an account' : 'Sign in'} to see the room you were invited to.`
                : isRegister
                  ? 'Start a room or join one with an invite link.'
                  : 'Welcome back.'}
            </p>
          </div>

          {notice && !formError && <div className="notice">{notice}</div>}
          {sessionExpired && !notice && !formError && <div className="notice">Your session ended. Sign in to carry on.</div>}
          {formError && (
            <div className="form-error" role="alert">
              {formError}
            </div>
          )}

          {isRegister && (
            <div className="field">
              <label htmlFor="name">Name</label>
              <input
                className="input"
                id="name"
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                {...fieldProps('name')}
              />
              {fieldError('name')}
            </div>
          )}

          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              className="input"
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              {...fieldProps('email')}
            />
            {fieldError('email')}
          </div>

          <div className="field">
            <div className="label-row">
              <label htmlFor="password">Password</label>
              {!isRegister && (
                <Link to="/forgot-password" state={{ email }} className="small">
                  Forgot password?
                </Link>
              )}
            </div>
            <input
              className="input"
              id="password"
              type="password"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              {...fieldProps('password')}
            />
            {fieldError('password') ?? (isRegister && <span className="hint">At least 8 characters.</span>)}
          </div>

          <button className="btn primary block" type="submit" disabled={submitting}>
            {isRegister ? (submitting ? 'Creating account…' : 'Create account') : submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="auth-foot">
          {isRegister ? 'Already have an account? ' : 'New to The Floor? '}
          {/* Pass `from` along so an invite link survives switching between the two forms. */}
          <Link to={isRegister ? '/login' : '/register'} state={location.state}>
            {isRegister ? 'Sign in' : 'Create an account'}
          </Link>
        </p>
        <p className="auth-foot">
          <Link to="/privacy">How we handle your data</Link>
        </p>
      </div>
    </div>
  )
}

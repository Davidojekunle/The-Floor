import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { Logo } from '../components/Logo'

/** Any address the app doesn't know: say so, and offer the way back. */
export function NotFoundPage() {
  const { user } = useAuth()
  return (
    <div className="center-screen">
      <div className="auth" style={{ width: 'min(420px, 100%)' }}>
        <Logo />
        <div className="invite">
          <span className="room-sq lg muted-sq">
            <Icon name="link" size={20} />
          </span>
          <div className="invite-head">
            <h1>This page doesn't exist</h1>
            <p className="muted">The link may be mistyped or out of date. Check it, or ask whoever sent it for a new one.</p>
          </div>
          {user ? (
            <Link className="btn primary block" to="/rooms">
              Go to your rooms
            </Link>
          ) : (
            <>
              <Link className="btn primary block" to="/login">
                Sign in
              </Link>
              <Link className="btn block" to="/">
                Go to the home page
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

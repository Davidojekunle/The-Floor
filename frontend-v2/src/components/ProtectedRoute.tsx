import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Logo } from './Logo'

export function ProtectedRoute() {
  const { user, loading, unreachable, retry } = useAuth()
  const location = useLocation()

  if (loading) return null
  if (unreachable) {
    // Offline or the API is down. The session may be fine, so don't send them to sign in.
    return (
      <div className="center-screen">
        <div className="auth" style={{ width: 'min(420px, 100%)' }}>
          <Logo />
          <div className="empty">
            <h2>Can't reach The Floor</h2>
            <p>Check your connection. You're still signed in.</p>
            <button className="btn primary" type="button" onClick={() => void retry()}>
              Try again
            </button>
          </div>
        </div>
      </div>
    )
  }
  if (!user) {
    // Keep the query string too, so invite links and filters survive signing in.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  return <Outlet />
}

import { useEffect, useState } from 'react'
import { Logo } from './Logo'

/**
 * While the session is being restored. Usually that's a blink, so nothing shows for the first 600 ms
 * (no flash). If it takes longer (a slow network, or the server asked us to wait a few seconds and
 * try again), say so instead of leaving a blank page.
 */
export function SessionPending() {
  const [stage, setStage] = useState<'hidden' | 'waiting' | 'slow'>('hidden')
  useEffect(() => {
    const a = setTimeout(() => setStage('waiting'), 600)
    const b = setTimeout(() => setStage('slow'), 5000)
    return () => {
      clearTimeout(a)
      clearTimeout(b)
    }
  }, [])
  if (stage === 'hidden') return null
  return (
    <div className="center-screen" role="status" aria-live="polite">
      <div className="auth" style={{ width: 'min(420px, 100%)' }}>
        <Logo />
        <div className="empty">
          <h2>Signing you in…</h2>
          {stage === 'slow' && (
            <>
              <p>This is taking longer than usual. The Floor may be busy or waking up; it'll keep trying.</p>
              <button className="btn" type="button" onClick={() => window.location.reload()}>
                Reload
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

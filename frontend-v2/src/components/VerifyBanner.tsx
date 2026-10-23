import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { resendVerification } from '../api/auth'
import { useAuth } from '../auth/useAuth'
import { Icon } from './Icon'
import { useToast } from './toastContext'

const HIDDEN = 'verify-banner-hidden' // for this browser tab only: it comes back next visit

function hiddenThisSession() {
  try {
    return sessionStorage.getItem(HIDDEN) === '1'
  } catch {
    return false
  }
}

/** Until the address is confirmed: a slim bar above every page, with a way to get the link again. */
export function VerifyBanner() {
  const { user } = useAuth()
  const toast = useToast()
  const [hidden, setHidden] = useState(hiddenThisSession)
  const resend = useMutation({
    mutationFn: resendVerification,
    onSuccess: () => toast(`Sent. Check ${user?.email}, and your spam folder.`),
    onError: (e) =>
      toast(e instanceof ApiError && e.code === 'RATE_LIMITED' ? 'Already sent a few. Try again in an hour.' : "Couldn't send it. Try again."),
  })
  if (!user || user.email_verified || hidden) return null

  const hide = () => {
    setHidden(true)
    try {
      sessionStorage.setItem(HIDDEN, '1')
    } catch {
      /* private mode: it just comes back on reload */
    }
  }

  return (
    <div className="verify-bar" role="status">
      <Icon name="inbox" size={16} />
      <span className="verify-text">
        Confirm your email. We sent a link to <strong>{user.email}</strong>.
      </span>
      <button className="link-btn" type="button" disabled={resend.isPending} onClick={() => resend.mutate()}>
        {resend.isPending ? 'Sending…' : 'Send again'}
      </button>
      <button className="icon-btn verify-close" type="button" aria-label="Hide for now" onClick={hide}>
        <Icon name="x" size={14} />
      </button>
    </div>
  )
}

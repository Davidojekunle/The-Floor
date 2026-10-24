import { useState } from 'react'
import { useAuth } from '../auth/useAuth'
import { Icon } from './Icon'

const KEY = 'announcement-dismissed' // remembers which message was hidden; a new one shows again

function dismissed(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

/** Staff's site-wide message (set on the admin page), above every page until hidden. */
export function AnnouncementBanner() {
  const { user } = useAuth()
  const [hidden, setHidden] = useState(dismissed)
  const text = user?.announcement
  if (!text || hidden === text) return null
  const hide = () => {
    setHidden(text)
    try {
      localStorage.setItem(KEY, text)
    } catch {
      /* private mode: it shows again next visit */
    }
  }
  return (
    <div className="announce-bar" role="status">
      <Icon name="bell" size={16} />
      <span className="verify-text">{text}</span>
      <button className="icon-btn verify-close" type="button" aria-label="Hide this message" onClick={hide}>
        <Icon name="x" size={14} />
      </button>
    </div>
  )
}

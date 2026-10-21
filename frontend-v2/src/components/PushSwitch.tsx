import type { PushState } from '../lib/push'
import { usePush } from '../lib/usePush'
import { Switch } from './Switch'

const DETAIL: Record<PushState, string> = {
  on: "Pop-ups for what you've chosen below, even when The Floor isn't open. Not while you're looking at it.",
  off: "Pop-ups for what you've chosen below, even when The Floor isn't open.",
  denied: "Blocked for this site in your browser's settings. Allow notifications there, then come back.",
  unsupported: "This browser can't show notifications.",
  'needs-install':
    'On iPhone and iPad: tap Share, then Add to Home Screen. Open The Floor from your Home Screen and turn this on there.',
}

// Shown as off, so turning it on (which registers again) is the obvious fix.
const UNSYNCED = "This device couldn't reach The Floor to sign up for pop-ups, so none will arrive. Turn this on to try again."

export function PushSwitch() {
  const { state, busy, unsynced, set } = usePush()
  if (!state) return null
  return (
    <Switch
      label="Notifications on this device"
      detail={unsynced ? UNSYNCED : DETAIL[state]}
      checked={state === 'on' && !unsynced}
      disabled={busy || (state !== 'on' && state !== 'off')}
      onChange={(on) => void set(on)}
    />
  )
}

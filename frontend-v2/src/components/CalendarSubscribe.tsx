import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getCalendarFeed, resetCalendarFeed } from '../api/calendar'
import { openInNewTab } from '../lib/googleCalendar'
import { ConfirmDialog } from './Dialog'
import { Icon } from './Icon'
import { useToast } from './toastContext'

/**
 * Subscribe to a calendar feed: your own work (no roomId) or everything in a room.
 * Google Calendar opens straight to "add this calendar"; Apple and Outlook take the copied link.
 */
export function CalendarSubscribe({ roomId, roomName }: { roomId?: string; roomName?: string }) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const key = ['calendar-feed', roomId ?? 'me']
  const feed = useQuery({ queryKey: key, queryFn: () => getCalendarFeed(roomId) })
  const [confirmReset, setConfirmReset] = useState(false)
  const reset = useMutation({
    mutationFn: () => resetCalendarFeed(roomId),
    onSuccess: (links) => {
      queryClient.setQueryData(key, links)
      setConfirmReset(false)
      toast('New link made. The old one has stopped working, so add the calendar again where you use it.')
    },
    onError: () => toast("The link couldn't be reset. Try again."),
  })

  const copy = async () => {
    if (!feed.data) return
    try {
      await navigator.clipboard.writeText(feed.data.url)
      toast('Calendar link copied.')
    } catch {
      toast("Couldn't copy. Select the link and copy it yourself.")
    }
  }

  if (feed.isPending) return <p className="faint small">Getting your calendar link…</p>
  if (feed.isError) return <p className="small">The calendar link didn't load. Reload the page to try again.</p>

  return (
    <div className="cal-sub">
      <div className="cal-sub-actions">
        <button className="btn primary" type="button" onClick={() => openInNewTab(feed.data.google_url)}>
          <Icon name="calendar" />
          Add to Google Calendar
        </button>
        <button className="btn" type="button" onClick={() => void copy()}>
          <Icon name="copy" />
          Copy link
        </button>
      </div>
      <p className="hint">
        {roomId ? `Every unfinished task in ${roomName ?? 'this room'}, on its due date.` : 'Your unfinished stages from all your rooms, on their due dates.'}{' '}
        Google Calendar refreshes it every few hours. For Apple Calendar or Outlook, copy the link and add it as a calendar subscription.
      </p>
      <p className="hint">
        Anyone with the link can see the task names, so keep it to yourself.{' '}
        <button className="link-btn" type="button" onClick={() => setConfirmReset(true)}>
          Reset link
        </button>
      </p>
      {confirmReset && (
        <ConfirmDialog
          title="Reset this calendar link?"
          body="The old link stops working straight away. You'll need to add the calendar again in Google Calendar or wherever you use it."
          confirmLabel="Reset link"
          onConfirm={() => reset.mutate()}
          onClose={() => setConfirmReset(false)}
        />
      )}
    </div>
  )
}

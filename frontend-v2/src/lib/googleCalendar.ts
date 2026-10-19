import { addDays, dayKey } from './dates'

/**
 * "Add to Google Calendar" for one item: opens Google Calendar with an all-day event filled in on the due
 * day (in the person's profile timezone). One-off: it won't follow later changes; the subscribe link does.
 */
export function googleCalendarEventUrl(opts: { title: string; dueIso: string; timeZone: string; details: string; link: string }) {
  const day = dayKey(opts.dueIso, opts.timeZone)
  const compact = (d: string) => d.replace(/-/g, '')
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: opts.title,
    dates: `${compact(day)}/${compact(addDays(day, 1))}`,
    details: `${opts.details}\n\n${opts.link}`,
  })
  return `https://calendar.google.com/calendar/render?${params.toString()}`
}

export function openInNewTab(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer')
}

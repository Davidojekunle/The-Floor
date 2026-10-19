import { apiRequest } from './client'

/** A private calendar subscription. Anyone with `url` can read the feed, so it can be reset. */
export type CalendarLinks = {
  url: string // https://…/calendar/<token>.ics
  webcal_url: string // the same as webcal://, which opens calendar apps directly
  google_url: string // opens Google Calendar's "add this calendar" page
}

const path = (roomId?: string) => (roomId ? `/rooms/${roomId}/calendar-feed` : '/me/calendar-feed')

export const getCalendarFeed = (roomId?: string) => apiRequest<CalendarLinks>(path(roomId))
export const resetCalendarFeed = (roomId?: string) => apiRequest<CalendarLinks>(`${path(roomId)}/reset`, { method: 'POST' })

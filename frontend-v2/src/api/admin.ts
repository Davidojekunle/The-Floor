import { apiRequest } from './client'

/** Staff only (everyone else gets a 404). Counts across the whole app: no names, titles or messages. */
export type AdminStats = {
  generated_at: string
  health: {
    database_ok: boolean
    database_ms: number
    migration: string | null
    started_at: string
    uptime_seconds: number
    loop_last_run_at: string | null // emails, digests and reminders; should be seconds ago
    loop_last_error_at: string | null
    loop_last_error: string | null
    emails_waiting: number
    oldest_waiting_email_at: string | null
    emails_sent_7d: number
    emails_failed_7d: number
    push_sent_since_start: number
    push_failed_since_start: number
    push_expired_since_start: number
  }
  people: { total: number; new_7d: number; new_30d: number; active_7d: number; active_30d: number; with_push: number; with_calendar: number }
  rooms: {
    total: number
    new_30d: number
    active_30d: number
    average_members: number
    pending_join_requests: number
    with_3_members: number
    real: number // 3+ active members and a stage done: the growth goal
  }
  /** Sign-ups and rooms by the ?ref= word people came with ("direct" without one), busiest first. */
  sources: { source: string; people: number; people_7d: number; rooms_started: number; real_rooms: number }[]
  work: {
    tasks_total: number
    tasks_open: number
    tasks_created_7d: number
    tasks_finished_7d: number
    proposals_waiting: number
    stages_done_7d: number
    stages_in_progress: number
    stages_overdue: number
    stages_blocked: number
    stages_stuck: number
  }
  activity: { messages_7d: number; updates_7d: number; nudges_30d: number; nudges_answered_30d: number }
  weeks: { week_start: string; signups: number; tasks_created: number; stages_done: number; messages: number }[]
  calls: {
    ready: boolean // LiveKit is configured on the server
    mode: 'off' | 'staff' | 'everyone'
    minutes_this_month: number // one person for one minute
    free_minutes: number
    calls_this_month: number
    live_now: number
    meetings_upcoming: number
  }
}

export const getAdminStats = () => apiRequest<AdminStats>('/admin/stats')

/** Site-wide switches staff change from the admin page. */
export type SiteSettings = {
  calls: 'off' | 'staff' | 'everyone'
  calls_ready: boolean // LiveKit is set up; calls can't be turned on without it
  signups_open: boolean
  notification_emails: boolean // security emails always go
  daily_digest: boolean
  push: boolean
  announcement: string | null
  task_assistant: 'off' | 'staff' | 'everyone' // who can "Describe your task"
  task_assistant_ready: boolean // ANTHROPIC_API_KEY is set on the server
}

export const getSiteSettings = () => apiRequest<SiteSettings>('/admin/settings')

export const updateSiteSettings = (change: Partial<SiteSettings>) =>
  apiRequest<SiteSettings>('/admin/settings', { method: 'PATCH', body: change })

/** For any visitor: whether sign-ups are open, and staff's announcement. */
export const getSite = () =>
  apiRequest<{ signups_open: boolean; announcement: string | null }>('/site', { auth: false })

/** Everyone who can open /admin. Only the owner (Me.is_owner) can add or remove them. */
export type AdminPerson = { id: string; name: string; email: string; is_owner: boolean }

export const listAdmins = () => apiRequest<AdminPerson[]>('/admin/admins')
export const addAdmin = (email: string) => apiRequest<AdminPerson[]>('/admin/admins', { method: 'POST', body: { email } })
export const removeAdmin = (userId: string) => apiRequest<AdminPerson[]>(`/admin/admins/${userId}`, { method: 'DELETE' })

/** The change log: switches turned on or off, admins added or removed. Newest first, last 50. */
export type AdminEvent = {
  id: string
  created_at: string
  actor_name: string
  action: 'setting_changed' | 'admin_added' | 'admin_removed'
  detail: { key?: string; old?: unknown; new?: unknown; name?: string; email?: string }
}

export const getAdminLog = () => apiRequest<AdminEvent[]>('/admin/log')

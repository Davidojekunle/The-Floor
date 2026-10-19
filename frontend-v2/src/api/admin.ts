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
  rooms: { total: number; new_30d: number; active_30d: number; average_members: number; pending_join_requests: number }
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
}

export const getAdminStats = () => apiRequest<AdminStats>('/admin/stats')

import { apiRequest } from './client'

/** Staff only while we try it (Me.task_assistant). Everyone else gets 404. */
export type AssistantTurn = { role: 'user' | 'assistant'; text: string }

export type DraftStageOut = {
  title: string
  assignee_id: string | null
  tag_id: string | null
  due_date: string | null // "YYYY-MM-DD" in my time zone
  parallel_with_previous: boolean
}

export type DraftTaskOut = {
  title: string
  description: string | null
  due_date: string // "YYYY-MM-DD"
  stages: DraftStageOut[]
}

export type AssistantReply = {
  conversation_id: string
  kind: 'questions' | 'draft'
  message: string
  questions: string[]
  draft: DraftTaskOut | null
  turns_left: number
  uses_left: number // new descriptions this room has left this week
}

export type AssistantStatus = { ready: boolean; limit: number; uses_left: number }

export const getAssistantStatus = (roomId: string) => apiRequest<AssistantStatus>(`/rooms/${roomId}/assistant`)

/** Nothing is created: a draft fills the task form, and the person presses Create there. */
export const askAssistant = (roomId: string, body: { conversation_id?: string; messages: AssistantTurn[] }) =>
  apiRequest<AssistantReply>(`/rooms/${roomId}/assistant/task-draft`, { method: 'POST', body })

import { apiRequest } from './client'

export type FeedbackKind = 'problem' | 'idea' | 'other'

/** Emailed to the support inbox; replying to it reaches the sender. */
export const sendFeedback = (body: { kind: FeedbackKind; message: string; page: string }) =>
  apiRequest<void>('/feedback', { method: 'POST', body })

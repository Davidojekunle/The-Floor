import { apiRequest } from './client'

export type RoomRole = 'head' | 'temp_head' | 'member'

export type RoomSummary = {
  id: string
  name: string
  my_role: RoomRole
  pending_count: number // pending_join_requests + pending_proposals
  pending_join_requests: number // only where I have join.manage
  pending_proposals: number // only where I have task.approve
  mine_actionable: number // tasks here where one of my stages needs me
  temp_head_expires_at: string | null // when my temp-head grant here ends
  unread_messages: number // chat messages since I last read (not mine, not deleted)
}

export type Theme = 'system' | 'light' | 'dark'

export type Me = {
  id: string
  name: string
  email: string
  timezone: string
  theme: Theme // saved on the account, follows you across devices
  pending_email: string | null // a new address waiting to be confirmed
  unread_notifications: number // the bell's badge
  rooms: RoomSummary[]
  is_staff: boolean // can open /admin (health and usage totals)
}

export type MeUpdate = { name?: string; timezone?: string; theme?: Theme }

export type RegisterInput = {
  name: string
  email: string
  password: string
  timezone: string
}

type LoginResponse = {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export function registerRequest(input: RegisterInput) {
  return apiRequest<unknown>('/auth/register', { method: 'POST', body: input, auth: false })
}

/** Also sets the refresh cookie. A wrong password is 401 INVALID_CREDENTIALS. */
export function loginRequest(email: string, password: string) {
  return apiRequest<LoginResponse>('/auth/login', {
    method: 'POST',
    body: { email, password },
    auth: false,
    session: true,
  })
}

/** Emails a reset link if the account exists. The answer is the same either way (no account probing). */
export const forgotPassword = (email: string) =>
  apiRequest<{ message: string }>('/auth/forgot-password', { method: 'POST', body: { email }, auth: false, session: true })

/** 400 RESET_TOKEN_INVALID for a bad, used, cancelled or expired link. Signs out every device. */
export const resetPassword = (token: string, newPassword: string) =>
  apiRequest<void>('/auth/reset-password', { method: 'POST', body: { token, new_password: newPassword }, auth: false, session: true })

/** Ends this browser's session and clears the cookie. Safe to repeat, even when already signed out. */
export const logoutRequest = () => apiRequest<void>('/auth/logout', { method: 'POST', auth: false, session: true })

/** Ends every session of this user, on every device. Needs a valid access token. */
export const logoutAllRequest = () => apiRequest<void>('/auth/logout-all', { method: 'POST', session: true })

export function getMe() {
  return apiRequest<Me>('/me')
}

/** Send only what changes. Returns the full /me. Other tabs and devices get `account_changed`. */
export const updateMe = (body: MeUpdate) => apiRequest<Me>('/me', { method: 'PATCH', body })

/**
 * Every other session ends at once; this tab gets a fresh access token and carries on.
 * Wrong current password: 401 INVALID_CREDENTIALS (`fields.current_password`). Same as now: 422 `fields.new_password`.
 */
export const changePassword = (currentPassword: string, newPassword: string) =>
  apiRequest<LoginResponse>('/auth/change-password', {
    method: 'POST',
    body: { current_password: currentPassword, new_password: newPassword },
    session: true,
  })

/** Sends a link to the new address (24 h) and a notice with a cancel link to the current one. 202. */
export const changeEmail = (newEmail: string, currentPassword: string) =>
  apiRequest<{ message: string }>('/auth/change-email', {
    method: 'POST',
    body: { new_email: newEmail, current_password: currentPassword },
    session: true,
  })

/** Cancel my pending change (signed in). */
export const cancelEmailChange = () => apiRequest<void>('/auth/change-email', { method: 'DELETE', session: true })

/** From the link sent to the new address. Needs the account's password, so a mistyped address can't take it. 204. */
export const confirmEmail = (token: string, currentPassword: string) =>
  apiRequest<void>('/auth/confirm-email', { method: 'POST', body: { token, current_password: currentPassword }, auth: false, session: true })

/** From the "this wasn't me" link sent to the old address. 204. */
export const cancelEmailChangeByLink = (token: string) =>
  apiRequest<void>('/auth/cancel-email-change', { method: 'POST', body: { token }, auth: false, session: true })

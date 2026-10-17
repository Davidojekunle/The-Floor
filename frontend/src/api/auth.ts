
import { apiRequest } from './client'

export type RoomRole = 'head' | 'temp_head' | 'member'

export type RoomSummary = {
  id: string
  name: string
  my_role: RoomRole
  pending_count: number
}

export type Me = {
  id: string
  name: string
  email: string
  timezone: string
  rooms: RoomSummary[]
}

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
  return apiRequest<unknown>('/auth/register', {
    method: 'POST',
    body: input,
    auth: false,
  })
}

export function loginRequest(email: string, password: string) {
  return apiRequest<LoginResponse>('/auth/login', {
    method: 'POST',
    body: { email, password },
    auth: false,
  })
}

export function getMe() {
  return apiRequest<Me>('/me')
}
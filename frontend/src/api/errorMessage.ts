import { ApiError } from './client'

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.fields) {
      const first = Object.values(err.fields)[0]
      if (first) return first
    }
    return err.message
  }
  return 'Something went wrong.'
}
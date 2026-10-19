import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { useToast } from '../components/toastContext'
import { useRoom } from './roomContext'

/**
 * Shared handling for a failed action in a room (works outside room pages too, e.g. My work):
 * - 403: our permissions changed (e.g. temp head expired). Toast the reason and reload the room.
 * - 404: we may have been removed. Reload the room (shows the no-access screen) and the room list.
 * Returns the message to show inline, if the caller wants one.
 */
export function useActionError(roomId: string) {
  const { refreshUser } = useAuth()
  const toast = useToast()
  const queryClient = useQueryClient()

  return useCallback(
    (err: unknown): string => {
      if (!(err instanceof ApiError)) return 'Something went wrong. Try again.'
      if (err.code === 'FORBIDDEN') {
        toast(err.message)
        void queryClient.invalidateQueries({ queryKey: ['room', roomId] })
        void queryClient.invalidateQueries({ queryKey: ['me-tasks'] })
      }
      if (err.code === 'NOT_FOUND') {
        void queryClient.invalidateQueries({ queryKey: ['room', roomId] })
        void queryClient.invalidateQueries({ queryKey: ['me-tasks'] })
        void refreshUser()
      }
      // Someone approved or changed a proposal under us: reload what we show.
      if (err.code === 'TASK_NOT_APPROVED' || err.code === 'ALREADY_APPROVED') {
        void queryClient.invalidateQueries({ queryKey: ['task', roomId] })
        void queryClient.invalidateQueries({ queryKey: ['tasks', roomId] })
        void refreshUser()
        return err.code === 'TASK_NOT_APPROVED'
          ? "This task isn't approved yet, so work can't start on it."
          : 'This task was already approved.'
      }
      return err.message
    },
    [toast, refreshUser, queryClient, roomId],
  )
}

/** useActionError for the room the current page is in. */
export function useRoomError() {
  return useActionError(useRoom().room.id)
}

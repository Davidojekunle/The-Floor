import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getNotificationSettings,
  muteRoom,
  unmuteRoom,
  updateNotificationSettings,
  type NotificationSettings,
} from '../api/notifications'
import { useToast } from '../components/toastContext'

type Switches = Partial<Omit<NotificationSettings, 'muted_rooms'>>
type Mute = { roomId: string; on: boolean }
type Before = NotificationSettings | undefined
const KEY = ['notification-settings']

/** Notification settings with optimistic switches: they flip at once and flip back if saving fails. */
export function useNotificationSettings() {
  const queryClient = useQueryClient()
  const toast = useToast()
  const query = useQuery({ queryKey: KEY, queryFn: getNotificationSettings })

  const optimistic = (change: (s: NotificationSettings) => NotificationSettings): Before => {
    const before = queryClient.getQueryData<NotificationSettings>(KEY)
    if (before) queryClient.setQueryData(KEY, change(before))
    return before
  }
  const saved = (s: NotificationSettings) => queryClient.setQueryData(KEY, s)
  const failed = (err: Error, before: Before) => {
    if (before) queryClient.setQueryData(KEY, before)
    toast(err.message || "Couldn't save that setting.")
  }

  const update = useMutation<NotificationSettings, Error, Switches, Before>({
    mutationFn: (body) => updateNotificationSettings(body),
    onMutate: (body) => optimistic((s) => ({ ...s, ...body })),
    onSuccess: saved,
    onError: (err, _v, before) => failed(err, before),
  })
  const mute = useMutation<NotificationSettings, Error, Mute, Before>({
    mutationFn: ({ roomId, on }) => (on ? muteRoom(roomId) : unmuteRoom(roomId)),
    onMutate: ({ roomId, on }) =>
      optimistic((s) => ({
        ...s,
        muted_rooms: on ? [...new Set([...s.muted_rooms, roomId])] : s.muted_rooms.filter((r) => r !== roomId),
      })),
    onSuccess: saved,
    onError: (err, _v, before) => failed(err, before),
  })

  return { settings: query.data, isPending: query.isPending, update: update.mutate, setMuted: mute.mutate }
}

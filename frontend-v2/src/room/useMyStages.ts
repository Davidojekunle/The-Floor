import { useQuery } from '@tanstack/react-query'
import { listMyTasks, type MyStage, type MyTask } from '../api/me'

export type MyStageItem = { task: MyTask; stage: MyStage }

const ORDER: Record<string, number> = { blocked: 0, in_progress: 1, todo: 2, locked: 3 }

/** My unfinished stages in one room, most urgent first. */
export function useMyStages(roomId: string) {
  const query = useQuery({
    queryKey: ['me-tasks', { room: roomId }],
    queryFn: () => listMyTasks({ room: roomId }),
  })

  const stages: MyStageItem[] = []
  for (const task of query.data?.items ?? []) {
    for (const stage of task.my_stages) {
      if (stage.status !== 'done') stages.push({ task, stage })
    }
  }
  stages.sort((a, b) => (ORDER[a.stage.status] ?? 9) - (ORDER[b.stage.status] ?? 9))

  return { stages, isPending: query.isPending, isError: query.isError }
}

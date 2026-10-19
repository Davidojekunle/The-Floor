import { ApiError } from '../api/client'
import {
  addStage,
  deleteStage,
  updateStage,
  updateTask,
  type StageUpdate,
  type TaskDetail,
  type TaskUpdate,
} from '../api/tasks'
import { endOfDayIso } from '../lib/dates'
import { FieldErrors, ownerFields, ownerOf, type DraftStage, type DraftTask } from './taskDraft'

/**
 * Apply the form to the task with the fewest calls, in an order the server's rules allow:
 * 1. remove deleted stages  2. update kept stages (fields + order)  3. insert new stages
 * 4. set "parallel" on a kept stage that only stops being first after the inserts.
 * The task's own due date moves before the stages when it gets later, and after them when it gets earlier,
 * so "a stage can't be due after the task" holds at every step.
 */
export async function saveTaskChanges(roomId: string, task: TaskDetail, d: DraftTask, tz: string): Promise<TaskDetail> {
  let latest = task
  const iso = (day: string) => (day ? endOfDayIso(day, tz) : null)
  const ms = (s: string | null) => (s ? new Date(s).getTime() : null) // server and browser format ISO differently

  const taskPatch: TaskUpdate = {}
  if (d.title.trim() !== task.title) taskPatch.title = d.title.trim()
  if ((d.description?.trim() || null) !== task.description) taskPatch.description = d.description?.trim() || null
  const newDue = iso(d.due)!
  if (ms(newDue) !== ms(task.due_date)) taskPatch.due_date = newDue
  const dueMovesLater = taskPatch.due_date !== undefined && ms(newDue)! > ms(task.due_date)!

  const run = async (call: Promise<TaskDetail>, at: number | null) => {
    try {
      latest = await call
    } catch (err) {
      // Put stage errors on the right row of the form.
      if (at !== null && err instanceof ApiError && err.fields)
        throw new FieldErrors(Object.fromEntries(Object.entries(err.fields).map(([k, v]) => [`stages.${at}.${k}`, v])))
      throw err
    }
  }

  if (Object.keys(taskPatch).length && (dueMovesLater || taskPatch.due_date === undefined))
    await run(updateTask(roomId, task.id, taskPatch), null)

  const kept = d.stages.filter((s) => s.id)
  const original = new Map(task.stages.map((s) => [s.id, s]))
  const removed = task.stages.filter((s) => !kept.some((k) => k.id === s.id))

  // If every old stage is being replaced, add the new ones first: a task can't drop to zero stages.
  if (kept.length === 0) {
    // Appended after the old stages, so "parallel" is legal even for the first; it's cleared once the old ones go.
    for (const [i, s] of d.stages.entries()) await run(addStage(roomId, task.id, newStageBody(s, i > 0 && s.parallel, iso)), i)
    for (const s of removed) await run(deleteStage(roomId, task.id, s.id), null)
  } else {
    for (const s of removed) await run(deleteStage(roomId, task.id, s.id), null)

    const deferredParallel: DraftStage[] = []
    for (const [j, s] of kept.entries()) {
      const before = original.get(s.id!)!
      const patch: StageUpdate = { position: j + 1 }
      if (s.title.trim() !== before.title) patch.title = s.title.trim()
      if (s.owner !== ownerOf(before).owner) Object.assign(patch, ownerFields(s.owner))
      const due = iso(s.due)
      if (ms(due) !== ms(before.due_date)) patch.due_date = due
      const wantParallel = d.stages.indexOf(s) > 0 && s.parallel
      if (wantParallel && j === 0) deferredParallel.push(s) // only legal once a new stage lands before it
      else if (wantParallel !== before.parallel_with_previous) patch.parallel_with_previous = wantParallel
      // Skip the call when nothing changes and the stage is already in place.
      const nowAt = latest.stages.find((x) => x.id === s.id)?.position
      if (Object.keys(patch).length === 1 && nowAt === j + 1) continue
      await run(updateStage(roomId, task.id, s.id!, patch), d.stages.indexOf(s))
    }

    for (const [i, s] of d.stages.entries()) {
      if (!s.id) await run(addStage(roomId, task.id, { ...newStageBody(s, i > 0 && s.parallel, iso), position: i + 1 }), i)
    }
    for (const s of deferredParallel)
      await run(updateStage(roomId, task.id, s.id!, { parallel_with_previous: true }), d.stages.indexOf(s))
  }

  if (Object.keys(taskPatch).length && !(dueMovesLater || taskPatch.due_date === undefined))
    await run(updateTask(roomId, task.id, taskPatch), null)

  return latest
}

function newStageBody(s: DraftStage, parallel: boolean, iso: (day: string) => string | null) {
  return { title: s.title.trim(), ...ownerFields(s.owner), due_date: iso(s.due), parallel_with_previous: parallel }
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

const LABELS: Record<string, string> = {
  locked: 'Locked',
  todo: 'To do',
  in_progress: 'In progress',
  blocked: 'Blocked',
  done: 'Done',
  not_started: 'Not started',
}

export function statusLabel(status: string): string {
  return LABELS[status] ?? status.replace(/_/g, ' ')
}

// Button text for moving a stage from one status to another.
export function actionLabel(current: string, target: string): string {
  if (current === 'locked' && target === 'todo') return 'Unlock early'
  if (current === 'locked' && target === 'in_progress') return 'Start early'
  if (current === 'done' && target === 'in_progress') return 'Reopen'
  if (current === 'blocked' && target === 'in_progress') return 'Unblock'
  if (target === 'in_progress') return 'Start'
  if (target === 'todo') return 'Back to to do'
  if (target === 'done') return 'Mark done'
  if (target === 'blocked') return 'Mark blocked'
  return statusLabel(target)
}
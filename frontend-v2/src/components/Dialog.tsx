import { useEffect, useId, useRef, type ReactNode } from 'react'
import { useIsPhone } from '../lib/useMedia'
import { Sheet } from './Sheet'

type Props = {
  title: ReactNode
  children?: ReactNode
  actions: ReactNode
  onClose: () => void
}

/** Focused confirmation or small form. Esc and a backdrop click close it. On phones it's a bottom sheet. */
export function Dialog(props: Props) {
  const phone = useIsPhone()
  if (phone)
    return (
      <Sheet title={props.title} onClose={props.onClose} footer={<div className="sheet-actions">{props.actions}</div>}>
        <div className="sheet-dialog">{props.children}</div>
      </Sheet>
    )
  return <CentredDialog {...props} />
}

function CentredDialog({ title, children, actions, onClose }: Props) {
  const titleId = useId()
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const first = box.current?.querySelector<HTMLElement>('[autofocus], input, textarea, select, button.primary, button.danger')
    first?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous?.focus()
    }
  }, [onClose])

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={box}>
        <h2 id={titleId}>{title}</h2>
        {children}
        <div className="actions">{actions}</div>
      </div>
    </div>
  )
}

/** A standard yes/no confirmation for destructive actions. */
export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  pending,
  error,
  onConfirm,
  onClose,
}: {
  title: ReactNode
  body: ReactNode
  confirmLabel: string
  pending?: boolean
  error?: string | null
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <Dialog
      title={title}
      onClose={onClose}
      actions={
        <>
          <button className="btn ghost" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn danger" type="button" onClick={onConfirm} disabled={pending}>
            {confirmLabel}
          </button>
        </>
      }
    >
      <p className="muted">{body}</p>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
    </Dialog>
  )
}

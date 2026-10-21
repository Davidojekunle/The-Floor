import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { useIsPhone } from '../lib/useMedia'
import { Icon } from './Icon'
import { Sheet } from './Sheet'

export type MenuItem = { label: ReactNode; onSelect: () => void; danger?: boolean } | 'divider'

type Props = {
  items: MenuItem[]
  label: string // accessible name for the trigger
  align?: 'left' | 'right'
  trigger?: ReactNode // defaults to a "…" icon button
  triggerClassName?: string
  header?: ReactNode // non-interactive text above the items
  /** Name the trigger with `label` (and a tooltip) even when it has content, e.g. when its text can be hidden. */
  labelTrigger?: boolean
}

/** The "…" menu that holds secondary and destructive actions. On phones it opens as an action sheet. */
export function Menu({ items, label, align = 'right', trigger, triggerClassName, header, labelTrigger }: Props) {
  const [open, setOpen] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const id = useId()
  const phone = useIsPhone()

  useEffect(() => {
    if (!open || phone) return
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, phone])

  return (
    <div className="menu-wrap" ref={wrap}>
      <button
        type="button"
        className={triggerClassName ?? 'icon-btn'}
        aria-label={label}
        title={labelTrigger ? label : undefined}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((o) => !o)}
      >
        {trigger ?? <Icon name="more" />}
      </button>
      {open && phone && (
        <Sheet
          label={label}
          onClose={() => setOpen(false)}
          footer={
            <button type="button" className="sheet-item cancel" onClick={() => setOpen(false)}>
              Cancel
            </button>
          }
        >
          {header && <div className="sheet-head">{header}</div>}
          <div className="sheet-list" role="menu" id={id}>
            {items.map((item, i) =>
              item === 'divider' ? (
                <hr key={i} />
              ) : (
                <button
                  key={i}
                  type="button"
                  role="menuitem"
                  className={`sheet-item${item.danger ? ' danger' : ''}`}
                  onClick={() => {
                    setOpen(false)
                    item.onSelect()
                  }}
                >
                  {item.label}
                </button>
              ),
            )}
          </div>
        </Sheet>
      )}
      {open && !phone && (
        <div className={`menu ${align}`} role="menu" id={id}>
          {header && <div className="mh">{header}</div>}
          {items.map((item, i) =>
            item === 'divider' ? (
              <hr key={i} />
            ) : (
              <button
                key={i}
                type="button"
                role="menuitem"
                className={item.danger ? 'danger' : undefined}
                onClick={() => {
                  setOpen(false)
                  item.onSelect()
                }}
              >
                {item.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  )
}

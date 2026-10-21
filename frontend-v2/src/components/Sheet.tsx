import { useCallback, useEffect, useId, useLayoutEffect, useRef, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { prefersReducedMotion } from '../lib/useMedia'
import { project, rubberband, spring, type SpringHandle } from '../lib/spring'

type Props = {
  /** Shown at the top; also the dialog's accessible name. */
  title?: ReactNode
  /** Accessible name when there's no visible title. */
  label?: string
  children: ReactNode
  /** Pinned below the scrolling body (actions). */
  footer?: ReactNode
  onClose: () => void
}

/**
 * The phone's version of a menu or dialog: a sheet that rises from the bottom edge.
 * - Drag it down by the top (or anywhere, when its content doesn't scroll). It follows the finger 1:1,
 *   resists past the top, and on release uses the finger's velocity: a flick closes it, a slow drag
 *   springs back, both continuing at the same speed with no seam.
 * - Escape, the scrim and Cancel close it the same way it arrived: back down.
 * - With reduced motion it simply appears and disappears.
 */
export function Sheet({ title, label, children, footer, onClose }: Props) {
  const panel = useRef<HTMLDivElement>(null)
  const scrim = useRef<HTMLDivElement>(null)
  const body = useRef<HTMLDivElement>(null)
  const anim = useRef<SpringHandle | null>(null)
  const offset = useRef(0)
  const closing = useRef(false)
  const dragged = useRef(false)
  const drag = useRef<{ id: number; y0: number; from: number; active: boolean; samples: { y: number; t: number }[] } | null>(null)
  const titleId = useId()
  const reduced = useRef(prefersReducedMotion())

  const height = () => panel.current?.offsetHeight || 400

  const apply = useCallback((y: number) => {
    offset.current = y
    if (panel.current) panel.current.style.transform = `translate3d(0, ${y}px, 0)`
    if (scrim.current) scrim.current.style.opacity = String(Math.min(1, Math.max(0, 1 - y / (panel.current?.offsetHeight || 400))))
  }, [])

  const animate = useCallback(
    (to: number, opts: Parameters<typeof spring>[3], done?: () => void) => {
      anim.current?.stop()
      anim.current = spring(offset.current, to, apply, opts, done)
    },
    [apply],
  )

  const close = useCallback(
    (velocity = 0) => {
      if (closing.current) return
      closing.current = true
      if (reduced.current) return onClose()
      animate(height(), { dampingRatio: 1, response: 0.28, velocity: Math.max(velocity, 0) }, onClose)
    },
    [animate, onClose],
  )

  // Arrive from below, critically damped (no bounce: nothing was thrown).
  useLayoutEffect(() => {
    if (reduced.current) return apply(0)
    apply(height())
    animate(0, { dampingRatio: 1, response: 0.34 })
    return () => anim.current?.stop()
  }, [apply, animate])

  // Focus the first control, keep Tab inside, close on Escape, and give focus back afterwards.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const focusables = () =>
      [...(panel.current?.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])') ?? [])].filter(
        (el) => !el.hasAttribute('disabled'),
      )
    // A text field is only focused when it asks to be (autoFocus): focusing one on a phone opens the keyboard,
    // which covers the bottom of the sheet and its buttons. Otherwise the first button, or the sheet itself.
    const first =
      panel.current?.querySelector<HTMLElement>('[autofocus]') ??
      focusables().find((el) => !el.matches('input, textarea, select, [contenteditable]')) ??
      panel.current
    first?.focus({ preventScroll: true })
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') return close()
      if (e.key !== 'Tab') return
      const els = focusables()
      if (!els.length) return
      const [a, z] = [els[0], els[els.length - 1]]
      if (e.shiftKey && document.activeElement === a) {
        e.preventDefault()
        z.focus()
      } else if (!e.shiftKey && document.activeElement === z) {
        e.preventDefault()
        a.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous?.focus?.({ preventScroll: true })
    }
  }, [close])

  // ---- dragging
  const canDragFrom = (target: EventTarget | null) => {
    const el = target as HTMLElement | null
    if (!el || el.closest('input, textarea, select')) return false
    if (el.closest('.sheet-grab, .sheet-title')) return true
    const b = body.current
    return !!b && b.scrollHeight <= b.clientHeight + 1 // nothing to scroll, so the whole sheet is a handle
  }

  const onPointerDown = (e: ReactPointerEvent) => {
    if (e.button !== 0 || closing.current || !canDragFrom(e.target)) return
    drag.current = { id: e.pointerId, y0: e.clientY, from: offset.current, active: false, samples: [{ y: e.clientY, t: e.timeStamp }] }
    dragged.current = false
  }

  const onPointerMove = (e: ReactPointerEvent) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    const dy = e.clientY - d.y0
    if (!d.active) {
      if (Math.abs(dy) < 8) return // a little hysteresis, so taps stay taps
      d.active = true
      dragged.current = true
      anim.current?.stop() // grab it mid-flight: continue from where it is now
      d.from = offset.current
      panel.current?.setPointerCapture(e.pointerId)
    }
    const y = d.from + (e.clientY - d.y0)
    apply(y < 0 ? rubberband(y, height()) : y)
    d.samples.push({ y: e.clientY, t: e.timeStamp })
    if (d.samples.length > 6) d.samples.shift()
  }

  const onPointerUp = (e: ReactPointerEvent) => {
    const d = drag.current
    drag.current = null
    if (!d || !d.active || d.id !== e.pointerId) return
    const first = d.samples.find((s) => e.timeStamp - s.t < 100) ?? d.samples[0]
    const dt = Math.max(1, e.timeStamp - first.t)
    const velocity = ((e.clientY - first.y) / dt) * 1000 // px/s, positive = downwards
    // Decide from where the flick is going, not where the finger let go.
    if (offset.current + project(velocity) > height() * 0.5) close(velocity)
    else animate(0, { dampingRatio: velocity < -300 ? 0.8 : 1, response: 0.3, velocity })
  }

  return createPortal(
    <div className="sheet-layer">
      <div className="sheet-scrim" ref={scrim} onClick={() => close()} aria-hidden="true" />
      <div
        className="sheet"
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-label={title ? undefined : label}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onClickCapture={(e) => {
          // A drag that ends over a button isn't a tap on it.
          if (dragged.current) {
            e.preventDefault()
            e.stopPropagation()
            dragged.current = false
          }
        }}
      >
        <div className="sheet-grab" aria-hidden="true">
          <span />
        </div>
        {title && (
          <h2 className="sheet-title" id={titleId}>
            {title}
          </h2>
        )}
        <div className="sheet-body" ref={body}>
          {children}
        </div>
        {footer && <div className="sheet-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}
